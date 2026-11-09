#include "sdkconfig.h"
#include "reference_relay.h"
#include <stdio.h>

#if CONFIG_CSI_ESPNOW_UART_RELAY
#include "gateway_io.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs.h"

static uint8_t local_role, local_mac[6], peer_mac[6], channel;
static uint32_t local_boot, peer_boot, known_peer_boot, changes, drops, retries;
static uint64_t nonce, peer_nonce, last_seen, last_sent;
static bool paired, ready;
static volatile bool active, fault;
static const char *reason = "";
static wl_stream_t stream;
static uint8_t queue[RR_QUEUE_BYTES];
static size_t queued, queue_peak;
static SemaphoreHandle_t queue_lock;
static rr_receive_t deliver;
static void *delivery_context;

bool rr_enabled(void) { return true; }
bool rr_paired(void) { return paired; }
bool rr_faulted(void) { return fault; }
const char *rr_failure_reason(void) { return reason; }
uint32_t rr_drops(void) { return drops; }
uint32_t rr_peer_changes(void) { return changes; }
uint32_t rr_retries(void) { return retries; }
uint8_t rr_channel(void) { return channel; }
bool rr_ready(void)
{
    return paired && ready && !fault &&
        (uint64_t)esp_timer_get_time() - last_seen < RR_PEER_TIMEOUT_US;
}
size_t rr_queued_bytes(void)
{
    if (!queue_lock) return 0;
    xSemaphoreTake(queue_lock, portMAX_DELAY);
    size_t n = queued;
    xSemaphoreGive(queue_lock);
    return n;
}
size_t rr_queue_peak(void) { return queue_peak; }
void rr_session_active(bool value) { active = value; }
void rr_fail(const char *value)
{
    if (!fault) { reason = value; ++drops; fault = true; ready = false; }
}
static bool save_peer_boot(uint32_t value)
{
    nvs_handle_t nvs;
    if (nvs_open("uart_relay", NVS_READWRITE, &nvs) != ESP_OK) return false;
    bool ok = nvs_set_u32(nvs, "peer_boot", value) == ESP_OK &&
              nvs_commit(nvs) == ESP_OK;
    nvs_close(nvs);
    return ok;
}
void rr_init(uint8_t role, const uint8_t mac[6], rr_receive_t receive, void *context)
{
    local_role = role; memcpy(local_mac, mac, 6);
    deliver = receive; delivery_context = context;
    queue_lock = xSemaphoreCreateMutex();
    if (!queue_lock || role > 1) abort();
    nonce = ((uint64_t)esp_random() << 32) | esp_random();
    if (!nonce) nonce = 1;
    nvs_handle_t nvs;
    if (nvs_open("uart_relay", NVS_READWRITE, &nvs) != ESP_OK) abort();
    uint8_t config[RR_PAIR_SIZE + 1]; size_t size = sizeof(config);
    bool found = nvs_get_blob(nvs, "pair", config, &size) == ESP_OK &&
                 size == sizeof(config) && !memcmp(config, "CRPS", 4);
    nvs_get_u32(nvs, "boot", &local_boot);
    nvs_get_u32(nvs, "peer_boot", &known_peer_boot);
    if (local_boot == UINT32_MAX) { nvs_close(nvs); rr_fail("boot_exhausted"); return; }
    ++local_boot;
    if (nvs_set_u32(nvs, "boot", local_boot) != ESP_OK || nvs_commit(nvs) != ESP_OK)
        abort();
    nvs_close(nvs);
    if (!found) return;
    const uint8_t *expected = config + (role ? 10 : 4);
    if (memcmp(expected, mac, 6)) { rr_fail("pair_identity"); return; }
    memcpy(peer_mac, config + (role ? 4 : 10), 6);
    channel = config[RR_PAIR_SIZE];
    if (!channel || channel > 13) { rr_fail("pair_channel"); return; }
    uint8_t current; wifi_second_chan_t second;
    ESP_ERROR_CHECK(esp_wifi_get_channel(&current, &second));
    if (current != channel)
        ESP_ERROR_CHECK(esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_now_set_pmk(config + 16));
    esp_now_peer_info_t peer = {.channel = channel, .ifidx = WIFI_IF_STA, .encrypt = true};
    memcpy(peer.peer_addr, peer_mac, 6); memcpy(peer.lmk, config + 32, 16);
    if (esp_now_is_peer_exist(peer_mac)) ESP_ERROR_CHECK(esp_now_del_peer(peer_mac));
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    /* Reference traffic values link margin over the CSI upload's MCS3 rate. */
    if (!gw_peer_set_mcs(peer_mac, 0)) abort();
    paired = true;
}
bool rr_pair(const uint8_t *p, size_t size)
{
    if (active || size != RR_PAIR_SIZE + 1 || memcmp(p, "CRPS", 4) ||
        memcmp(p + (local_role ? 10 : 4), local_mac, 6) ||
        !memcmp(p + 4, p + 10, 6) || (p[4] & 1) || (p[10] & 1) ||
        !p[RR_PAIR_SIZE] || p[RR_PAIR_SIZE] > 13) return false;
    nvs_handle_t nvs;
    if (nvs_open("uart_relay", NVS_READWRITE, &nvs) != ESP_OK) return false;
    bool ok = nvs_set_blob(nvs, "pair", p, size) == ESP_OK &&
              nvs_set_u32(nvs, "peer_boot", 0) == ESP_OK && nvs_commit(nvs) == ESP_OK;
    nvs_close(nvs);
    return ok;
}
bool rr_send(uint8_t type, const uint8_t *p, size_t size)
{
    if (fault || !paired || !type || size > WL_PAYLOAD - 4) return false;
    if (xSemaphoreTake(queue_lock, pdMS_TO_TICKS(5)) != pdTRUE) {
        rr_fail("queue_lock"); return false;
    }
    bool ok = size + 3 <= sizeof(queue) - queued;
    if (ok) {
        queue[queued++] = type; wl_w16(queue + queued, size); queued += 2;
        memcpy(queue + queued, p, size); queued += size;
        if (queued > queue_peak) queue_peak = queued;
    }
    xSemaphoreGive(queue_lock);
    if (!ok) rr_fail("source_overflow");
    return ok;
}
static bool receive_block(const uint8_t *p, size_t size, void *context)
{
    (void)context;
    static uint8_t decoded[WL_LOGICAL];
    if (!size || p[0] > 1) return false;
    size_t n = p[0] ? wl_decompress(p + 1, size - 1, decoded, sizeof(decoded)) : size - 1;
    if (!p[0] && n <= sizeof(decoded)) memcpy(decoded, p + 1, n);
    if (!wl_frames_valid(decoded, n)) return false;
    const uint8_t *frame = decoded;
    while (n) {
        size_t count = wl_u16(frame + 1);
        if (!deliver(frame[0], frame + 3, count, delivery_context)) return false;
        frame += count + 3; n -= count + 3;
    }
    return true;
}
bool rr_receive(const uint8_t source[6], const uint8_t *p, size_t size)
{
    if (size < 4 || memcmp(p, "CRL1", 4)) return false;
    /* Never accept an unpaired sender, even if its CRC/session fields match. */
    if (!paired || memcmp(source, peer_mac, 6) ||
        !rr_packet_valid(p, size, local_role)) return true;
    uint32_t boot = wl_u32(p + 8); uint64_t remote_nonce = wl_u64(p + 12);
    if (!wl_epoch_valid(known_peer_boot, peer_boot, peer_nonce, boot, remote_nonce))
        return true;
    if (boot != peer_boot) {
        if (peer_boot) {
            ++changes;
            if (active) { rr_fail("peer_restart"); return true; }
        }
        if (boot > known_peer_boot && !save_peer_boot(boot)) {
            rr_fail("peer_boot_store"); return true;
        }
        /* A new authenticated peer epoch may recover an ended run. Preserve
         * counters, discard old bytes, and never revive an active session. */
        if (!active && fault && strcmp(reason, "peer_boot_store") &&
            strcmp(reason, "boot_exhausted") && strcmp(reason, "pair_identity") &&
            strcmp(reason, "pair_channel")) { fault = false; reason = ""; }
        known_peer_boot = peer_boot = boot; peer_nonce = remote_nonce;
        memset(&stream, 0, sizeof(stream)); ready = false; last_sent = 0;
        /* Requests admitted before a first handshake are retained. On an idle
         * restart old requests are discarded; callers must rediscover first. */
        if (changes) {
            xSemaphoreTake(queue_lock, portMAX_DELAY); queued = 0;
            xSemaphoreGive(queue_lock);
        }
    }
    last_seen = esp_timer_get_time();
    if (wl_u64(p + 20) != nonce) return true;
    if (p[6]) {
        if (!fault) {
            static char peer_reason[48];
            snprintf(peer_reason, sizeof(peer_reason), "peer_%s", rr_fault_name(p[7]));
            rr_fail(peer_reason);
        }
        return true;
    }
    if (fault) return true;
    ready = true;
    if (!wl_stream_ack(&stream, wl_u32(p + 32), p[36])) {
        rr_fail("invalid_ack"); return true;
    }
    if (wl_u16(p + 37) && !wl_stream_receive(&stream, wl_u32(p + 28),
            p + RR_HEADER, wl_u16(p + 37), receive_block, NULL))
        rr_fail("delivery_failed");
    /* Acknowledge promptly, independently of outbound data availability. */
    if (wl_u16(p + 37)) last_sent = 0;
    return true;
}
void rr_poll(void)
{
    if (!paired) return;
    uint64_t now = esp_timer_get_time();
    if (active && (!ready || now - last_seen >= RR_PEER_TIMEOUT_US))
        rr_fail("peer_timeout");
    for (unsigned i = 0; i < WL_WINDOW; ++i)
        if (stream.tx[i].used && now - stream.tx[i].created >= RR_LIFETIME_US)
            rr_fail("packet_expired");
    if (rr_ready()) {
        static uint8_t logical[WL_LOGICAL], packed[WL_PAYLOAD];
        for (unsigned i = 0; i < WL_WINDOW; ++i) {
            if (stream.next_tx - stream.acknowledged >= WL_WINDOW) break;
            xSemaphoreTake(queue_lock, portMAX_DELAY);
            size_t n = 0;
            while (n < queued) {
                size_t frame = wl_u16(queue + n + 1) + 3;
                if (frame > sizeof(logical) - n) break;
                n += frame;
            }
            if (!n) { xSemaphoreGive(queue_lock); break; }
            memcpy(logical, queue, n);
            xSemaphoreGive(queue_lock);
            /* Compression can outlast the UART producer's 5 ms lock wait.
             * This task is the sole queue consumer; producers only append.
             * Encode our private prefix without holding their admission lock. */
            size_t consumed = 0;
            size_t encoded = wl_encode_frames(logical, n, packed, sizeof(packed), &consumed);
            wl_slot_t *slot = encoded ? wl_stream_add(&stream, packed, encoded, now) : NULL;
            if (!slot) { rr_fail("encode_failed"); break; }
            xSemaphoreTake(queue_lock, portMAX_DELAY);
            memmove(queue, queue + consumed, queued - consumed); queued -= consumed;
            xSemaphoreGive(queue_lock);
        }
    }
    if (!gw_send_idle()) return;
    wl_slot_t *chosen = NULL;
    if (rr_ready()) {
        for (unsigned i = 0; i < WL_WINDOW; ++i) {
            wl_slot_t *slot = &stream.tx[i];
            if (slot->used && (!slot->sent || now - slot->sent >= 30000) &&
                (!chosen || slot->sequence < chosen->sequence)) chosen = slot;
        }
    }
    if (!chosen && last_sent && now - last_sent < RR_HEARTBEAT_US) return;
    static uint8_t packet[RR_PACKET];
    size_t size = rr_packet_encode(packet, local_role, fault, local_boot, nonce,
                                   peer_nonce, &stream, chosen);
    if (fault) {
        packet[7] = rr_fault_code(reason);
        csi_serial_write_u32(packet + size - 4, csi_serial_crc32(packet, size - 4));
    }
    if (gw_send(peer_mac, packet, size, 0)) {
        last_sent = now;
        if (chosen) { if (chosen->sent) ++retries; chosen->sent = now; }
    }
}
#else
bool rr_enabled(void) { return false; }
bool rr_pair(const uint8_t *p, size_t n) { (void)p; (void)n; return false; }
void rr_init(uint8_t r, const uint8_t m[6], rr_receive_t f, void *c)
{ (void)r; (void)m; (void)f; (void)c; }
bool rr_receive(const uint8_t m[6], const uint8_t *p, size_t n)
{ (void)m; (void)p; (void)n; return false; }
bool rr_send(uint8_t t, const uint8_t *p, size_t n)
{ (void)t; (void)p; (void)n; return false; }
void rr_poll(void) {}
void rr_session_active(bool value) { (void)value; }
void rr_fail(const char *reason) { (void)reason; }
bool rr_paired(void) { return false; }
bool rr_ready(void) { return false; }
bool rr_faulted(void) { return false; }
const char *rr_failure_reason(void) { return "disabled"; }
uint32_t rr_drops(void) { return 0; }
uint32_t rr_peer_changes(void) { return 0; }
uint32_t rr_retries(void) { return 0; }
size_t rr_queued_bytes(void) { return 0; }
size_t rr_queue_peak(void) { return 0; }
uint8_t rr_channel(void) { return 0; }
#endif
