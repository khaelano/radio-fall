"""Run the actual transmitter control state machine with a deterministic clock."""

import shutil
import subprocess
from pathlib import Path

import pytest

from fall_detection.radio.ble_config import BleTransportConfig


def test_sensing_send_policy_bounds_pending_frames_and_rotates_without_wrap(tmp_path):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler unavailable")
    source = tmp_path / "send.c"
    source.write_text("""
#include <assert.h>
#include "sensing_send_policy.h"
int main(void) {
    csi_sensing_send_policy_t p = {0};
    for (unsigned i=0; i<4; ++i) assert(csi_sensing_reserve(&p, i));
    assert(p.pending_mask == 15);
    for (unsigned i=0; i<4; ++i) assert(!csi_sensing_reserve(&p, i));
    assert(p.busy_skips == 4 && p.pending_mask == 15);
    csi_sensing_complete(&p, 3);
    assert(p.pending_mask == 7 && csi_sensing_reserve(&p, 3));
    csi_sensing_complete(&p, 0);
    csi_sensing_complete(&p, 0);
    assert(p.pending_mask == 14);
    assert(!csi_sensing_reserve(&p, 4));
    csi_sensing_result(&p, 3, false, 1000, 100000);
    assert(!csi_sensing_reserve_at(&p, 3, 100999));
    assert(p.backoff_skips == 1);
    assert(csi_sensing_reserve_at(&p, 3, 101000));
    csi_sensing_result(&p, 3, true, 101001, 100000);
    assert(csi_sensing_reserve_at(&p, 3, 101001));
    for (unsigned count=1; count<=4; ++count) {
        for (unsigned delta=0; delta<8; ++delta) {
            uint32_t sequence = UINT32_MAX-delta;
            unsigned seen=0;
            for (unsigned offset=0; offset<count; ++offset) {
                unsigned peer=csi_sensing_peer(sequence, offset, count);
                assert(peer<count && !(seen & (1U<<peer)));
                seen |= 1U<<peer;
            }
            assert(seen == (1U<<count)-1);
        }
    }
}
""")
    executable = tmp_path / "send"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-I",
            "src/firmware/radio/transmitter/main",
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True)


def test_transmitter_requires_start_and_fresh_host_control(tmp_path):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler unavailable")
    (tmp_path / "freertos").mkdir()
    (tmp_path / "sdkconfig.h").write_text(
        "#define CONFIG_CSI_BLE_SCHEDULER 1\n"
        "#define CONFIG_CSI_CONTROL_TIMEOUT_MS 3000\n"
    )
    (tmp_path / "esp_random.h").write_text(
        "#include <stdint.h>\nstatic inline uint32_t esp_random(void) { return 11; }\n"
    )
    (tmp_path / "esp_timer.h").write_text(
        """
#include <stdint.h>
#include <stdlib.h>
extern uint64_t test_now;
typedef void *esp_timer_handle_t;
typedef struct { void (*callback)(void *); const char *name; } esp_timer_create_args_t;
#define ESP_ERROR_CHECK(value) do { if (value) abort(); } while (0)
static inline int64_t esp_timer_get_time(void) { return test_now; }
static inline int esp_timer_create(const esp_timer_create_args_t *a, esp_timer_handle_t *t) { return 0; }
static inline int esp_timer_stop(esp_timer_handle_t t) { return 0; }
static inline int esp_timer_start_once(esp_timer_handle_t t, uint64_t us) { return 0; }
"""
    )
    (tmp_path / "freertos/FreeRTOS.h").write_text(
        """
#pragma once
typedef int portMUX_TYPE;
typedef void *QueueHandle_t;
typedef void *TaskHandle_t;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)0)
#define portEXIT_CRITICAL(p) ((void)0)
#define pdMS_TO_TICKS(v) (v)
#define portMAX_DELAY 0
#define pdTRUE 1
#define pdPASS 1
"""
    )
    (tmp_path / "freertos/queue.h").write_text(
        """
#include "FreeRTOS.h"
static inline QueueHandle_t xQueueCreate(int n, int s) { return (void *)1; }
static inline int xQueueReceive(QueueHandle_t q, void *p, int ticks) { return 0; }
static inline int xQueueSend(QueueHandle_t q, const void *p, int ticks) { return 1; }
"""
    )
    (tmp_path / "freertos/task.h").write_text(
        """
#include "FreeRTOS.h"
static inline TaskHandle_t xTaskGetCurrentTaskHandle(void) { return (void *)1; }
static inline int xTaskNotifyGive(TaskHandle_t t) { return 1; }
static inline int ulTaskNotifyTake(int clear, int ticks) { return 1; }
static inline int xTaskCreate(void (*f)(void *), const char *n, int s, void *p, int pri, void *out) { return 1; }
"""
    )
    config = BleTransportConfig().encode(
        123, 4, 80, receiver_macs=("00:00:00:00:00:00",) * 4
    )
    source = tmp_path / "control.c"
    source.write_text(
        """
#include <assert.h>
#include "ble_transmitter.h"
uint64_t test_now = 1000000;
static bool write_frame(uint8_t t, const uint8_t *p, size_t n) { return true; }
int main(void) {
    csi_radio_profile_t profile = {.receiver_count=4, .nominal_rate_hz=80};
    csi_ble_config_t out; uint32_t boot, generation, before;
    uint8_t response[64], command[16] = {0};
    uint8_t config[] = {CONFIG_BYTES};
    csi_ble_tx_init(&profile, write_frame);
    assert(!csi_ble_tx_snapshot(&out, &boot, &generation));
    assert(csi_ble_tx_control(config, sizeof(config), response) == 2);
    assert(!csi_ble_tx_snapshot(&out, &boot, &generation));
    memcpy(command, "CBGO", 4); csi_clock_write_u64(command+4, 123);
    assert(csi_ble_tx_control(command, 12, response) == 2);
    assert(csi_ble_tx_snapshot(&out, &boot, &before));
    test_now += 2999999;
    assert(csi_ble_tx_snapshot(&out, &boot, &generation));
    memcpy(command, "CBCK", 4);
    assert(csi_ble_tx_control(command, 16, response) == 40);
    test_now += 2999999;
    assert(csi_ble_tx_snapshot(&out, &boot, &generation));
    test_now += 1;
    assert(!csi_ble_tx_snapshot(&out, &boot, &generation));
    /* A clock poll cannot restart an expired sensing run. */
    assert(csi_ble_tx_control(command, 16, response) == 40);
    assert(!csi_ble_tx_snapshot(&out, &boot, &generation));
    memcpy(command, "CBGO", 4); csi_clock_write_u64(command+4, 123);
    assert(csi_ble_tx_control(command, 12, response) == 2);
    assert(csi_ble_tx_snapshot(&out, &boot, &generation));
    assert(generation != before);
    memcpy(command, "CBST", 4);
    assert(csi_ble_tx_control(command, 12, response) == 2);
    assert(!csi_ble_tx_snapshot(&out, &boot, &generation));
}
""".replace("CONFIG_BYTES", ",".join(str(b) for b in config))
    )
    root = Path("src/firmware/radio")
    executable = tmp_path / "control"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-I",
            str(tmp_path),
            "-I",
            str(root / "common/include"),
            "-I",
            str(Path("tests/radio/fixtures/legacy_ble_firmware")),
            str(source),
            str(Path("tests/radio/fixtures/legacy_ble_firmware/ble_transmitter.c")),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True)
