#ifndef CSI_GATEWAY_PROTOCOL_H
#define CSI_GATEWAY_PROTOCOL_H
#include "csi_clock_protocol.h"

#define GW_CONFIG_SIZE 108
#define GW_SENSING_SIZE 180
#define GW_ENVELOPE_HEADER 40
#define GW_MAX_PACKET 1400
#define GW_STATUS_SIZE 96
#define GW_CLOCK_SIZE 60
#define GW_ACK_SIZE 34
#define GW_MAX_OUTSTANDING 8
#define GW_BITMAP_SIZE 72
#define GW_CONTROL 20
#define GW_RESPONSE 21
#define GW_ROUND 22
#define GW_EVENT 23
#define GW_DATA 24
#define GW_ACK 25
#define GW_CAPTURE 0
#define GW_SWITCH_2G 1
#define GW_UPLOAD 2
#define GW_RETURN 3
#define GW_CONFIRM 4
#define GW_FAULT 5

typedef struct {
    uint8_t wire[GW_CONFIG_SIZE];
    uint64_t run;
    uint16_t rate, slot_ms, start_ms, return_ms, age_ms, ack_ms, early_idle_ms, revisit_ms, send_guard_ms;
    bool bitmap_ack, measure_sends, application_ack;
    uint8_t count, sensing_channel, channel, capacity, outstanding, retries, allowance, backhaul_mcs;
} gw_config_t;

static inline bool gw_check(const uint8_t *p, size_t n, const char *magic, size_t size)
{
    return p && n == size && n >= 8 && !memcmp(p, magic, 4) &&
        csi_serial_crc32(p, n-4) == csi_clock_read_u32(p+n-4);
}
static inline void gw_crc(uint8_t *p, size_t n)
{
    csi_clock_write_u32(p+n-4, csi_serial_crc32(p, n-4));
}
static inline bool gw_config_decode(const uint8_t *p, size_t n, gw_config_t *c)
{
    if (!gw_check(p,n,"CGCF",GW_CONFIG_SIZE) || p[4]<1 || p[4]>7 || p[5]<1 || p[5]>4) return false;
    memset(c,0,sizeof(*c));memcpy(c->wire,p,n);
    c->count=p[5];c->sensing_channel=p[6];c->channel=p[7];c->run=csi_clock_read_u64(p+8);
    c->rate=csi_clock_read_u16(p+16);c->slot_ms=csi_clock_read_u16(p+18);
    c->start_ms=csi_clock_read_u16(p+20);c->return_ms=csi_clock_read_u16(p+22);
    c->age_ms=csi_clock_read_u16(p+24);c->ack_ms=csi_clock_read_u16(p+26);
    c->capacity=p[28];c->outstanding=p[29];c->retries=p[30];c->allowance=p[31];
    c->early_idle_ms=p[4]>=3?p[100]:(p[4]==2?csi_clock_read_u16(p+100):0);
    c->revisit_ms=p[4]>=3?(uint16_t)p[101]*5:0;
    c->send_guard_ms=p[4]>=3?p[102]:10;
    c->bitmap_ack=p[4]>=3&&(p[103]&1);c->measure_sends=p[4]>=3&&(p[103]&2);
    c->application_ack=!(p[4]>=5&&(p[103]&4));
    c->backhaul_mcs=p[4]>=6?(p[103]>>3)&3:0;
    if(!c->application_ack&&(c->retries||c->bitmap_ack))return false;
    if(!c->run || c->sensing_channel<36 || c->channel<1 || c->channel>13 ||
       c->rate<50 || c->rate>(p[4]>=6?120:100) || c->slot_ms<20 || c->slot_ms>500 ||
       !c->start_ms || c->start_ms>100 || !c->return_ms || c->return_ms>100 ||
       c->start_ms+c->return_ms>=c->slot_ms || !c->age_ms || c->age_ms>1000 ||
       !c->ack_ms || c->ack_ms>c->age_ms || !c->capacity || c->capacity>(p[4]>=7?96:64) ||
       !c->outstanding || c->outstanding>(p[4]==1?4:GW_MAX_OUTSTANDING) || c->retries>(p[4]>=4?3:1) ||
       !c->allowance || c->allowance>64 || c->early_idle_ms>20 ||
       c->early_idle_ms>=c->slot_ms-c->start_ms-c->return_ms ||
       !c->send_guard_ms || c->send_guard_ms>20 || c->send_guard_ms>=c->slot_ms-c->start_ms-c->return_ms ||
       c->revisit_ms>1000 || (p[4]>=3?(p[103]&~(p[4]>=6?31U:(p[4]>=5?7U:3U))):(p[4]==1?csi_clock_read_u32(p+100):csi_clock_read_u16(p+102)))) return false;
    for(unsigned i=68;i<100;++i)
        if(!((p[i]>='0'&&p[i]<='9')||(p[i]>='a'&&p[i]<='f')))return false;
    return true;
}
/* Version 4 permits a bounded retry budget across later grants. Expired work
 * cannot become eligible again; each grant's existing send cutoff still applies. */
static inline bool gw_batch_ready(const gw_config_t *c,uint8_t attempts,
                                  uint64_t sent,uint64_t oldest,uint64_t now)
{
    if(c->wire[4]>=4 && (now<oldest || now-oldest>=(uint64_t)c->age_ms*1000))return false;
    if(!c->application_ack)return !attempts;
    return !attempts || (attempts<=c->retries && now>=sent && now-sent>=(uint64_t)c->ack_ms*1000);
}
static inline int gw_slot(const gw_config_t *c, const uint8_t *mac)
{
    for(unsigned i=0;i<c->count;++i)if(!memcmp(c->wire+44+6*i,mac,6))return i;
    return -1;
}
/* Single authority; no successor is issued before the prior return is confirmed.
 * A late/lost grant expires. Even a receiver which never departed must explicitly
 * confirm the expired grant on 5 GHz before its successor can be issued. */
typedef struct {
    uint32_t id;
    uint8_t owner, next;
    bool active, returned, probing;
    uint64_t start, end;
    uint64_t next_allowed[4];
} gw_schedule_t;
/* A return request resumes sensing probes only. It is not a return proof and
 * cannot unlock another departure. The actual sensing-frame witness still does. */
static inline bool gw_schedule_probe(gw_schedule_t *s,uint8_t owner,uint32_t id,
                                     uint64_t now,uint8_t state)
{
    if(!s->active || s->returned || s->probing || owner!=s->owner || id!=s->id ||
       now<s->start || state!=GW_CONFIRM)return false;
    s->probing=true;return true;
}
static inline bool gw_schedule_return(gw_schedule_t *s, uint8_t owner, uint32_t id,
                                      uint64_t now, uint8_t state)
{
    if(!s->active || s->returned || owner!=s->owner || id!=s->id || now<s->start || state!=GW_CAPTURE)return false;
    s->returned=true;
    return true;
}
static inline bool gw_schedule_next(gw_schedule_t *s, const gw_config_t *c, uint64_t now)
{
    if(s->active && !s->returned)return false;
    uint64_t next_start=now+2*(1000000U/c->rate);
    /* A confirmed owner cannot re-enter its handled grant. Announce the next
     * owner now, while retaining the old slot end as the departure barrier. */
    if(s->active && next_start<s->end)next_start=s->end;
    if(next_start<s->next_allowed[s->next])next_start=s->next_allowed[s->next];
    if(++s->id==0)++s->id;
    s->returned=false;s->probing=false;s->owner=s->next;s->next=(s->next+1)%c->count;s->active=true;
    s->start=next_start;s->end=s->start+(uint64_t)c->slot_ms*1000;
    s->next_allowed[s->owner]=s->start+(uint64_t)c->revisit_ms*1000;
    return true;
}
/* Recover before a scheduled sensing round inside the slot, rather than
 * retuning after that round and waiting a whole period for a return witness. */
static inline uint64_t gw_return_cutoff(const gw_config_t *c, uint64_t end,
                                        uint64_t observed_round)
{
    uint64_t guard=(uint64_t)c->start_ms*1000;
    uint64_t reserve=(uint64_t)c->return_ms*1000;
    uint64_t period=1000000U/c->rate;
    if(end<=guard || observed_round>end-guard)return 0;
    uint64_t witness=observed_round+((end-guard-observed_round)/period)*period;
    return witness>reserve?witness-reserve:0;
}
static inline bool gw_omit_sensing(const gw_config_t *c, const gw_schedule_t *s,
                                   unsigned receiver, uint64_t round, uint64_t now)
{
    uint64_t witness=gw_return_cutoff(c,s->end,round)+(uint64_t)c->return_ms*1000;
    return s->active && !s->probing && receiver==s->owner &&
        now>=s->start+(uint64_t)c->start_ms*1000 && now<witness;
}
#define GW_EXIT_NONE 0
#define GW_EXIT_COMPLETE 1
#define GW_EXIT_IDLE 2
#define GW_EXIT_DEADLINE 3
static inline unsigned gw_upload_exit(const gw_config_t *c,uint64_t now,
    uint64_t deadline,uint64_t last_work,bool sender_idle,bool work_ready,bool complete)
{
    if(now>=deadline)return GW_EXIT_DEADLINE;
    if(!c->early_idle_ms || !sender_idle)return GW_EXIT_NONE;
    if(complete || deadline-now<=(uint64_t)c->send_guard_ms*1000)return GW_EXIT_COMPLETE;
    if(!work_ready && now>=last_work && now-last_work>=(uint64_t)c->early_idle_ms*1000)
        return GW_EXIT_IDLE;
    return GW_EXIT_NONE;
}
static inline size_t gw_sensing_encode(uint8_t *p, const csi_sensing_packet_t *packet,
    const gw_config_t *c, uint32_t boot, const gw_schedule_t *s)
{
    memset(p,0,GW_SENSING_SIZE);csi_sensing_encode(p,GW_SENSING_SIZE,packet);
    p[4]=4;csi_clock_write_u16(p+6,GW_SENSING_SIZE);memcpy(p+40,c->wire,GW_CONFIG_SIZE);
    csi_clock_write_u32(p+148,boot);csi_clock_write_u32(p+152,s->id);
    p[156]=s->owner;p[157]=s->active;
    csi_clock_write_u64(p+160,s->start);csi_clock_write_u64(p+168,s->end);
    gw_crc(p,GW_SENSING_SIZE);return GW_SENSING_SIZE;
}
static inline bool gw_envelope_valid(const uint8_t *p,size_t n)
{
    return n>GW_ENVELOPE_HEADER+4 && n<=GW_MAX_PACKET &&
        gw_check(p,n,"CGWY",n) && p[4]==1 && !p[5] && csi_clock_read_u16(p+6)==40 &&
        csi_clock_read_u64(p+8) && !csi_clock_read_u32(p+36) &&
        n==44+csi_clock_read_u16(p+34);
}
/* Explicit IDs make bitmap acceptance selective across missing batches and
 * sequence wrap. Unused ID cells are zero and never interpreted. */
static inline bool gw_bitmap_valid(const uint8_t *p,size_t n,bool response)
{
    if(!gw_check(p,n,response?"CGPB":"CGPQ",GW_BITMAP_SIZE)||p[4]!=1||
       !p[5]||p[5]>GW_MAX_OUTSTANDING||p[7]||csi_clock_read_u16(p+30)||
       !csi_clock_read_u64(p+8)||(!response&&p[6])||(p[6]&~((1U<<p[5])-1)))return false;
    for(unsigned i=0;i<8;++i){
        uint32_t id=csi_clock_read_u32(p+36+4*i);
        if(i>=p[5]){if(id)return false;continue;}
        for(unsigned j=0;j<i;++j)if(id==csi_clock_read_u32(p+36+4*j))return false;
    }
    return true;
}
static inline bool gw_bitmap_matches(const uint8_t *request,const uint8_t *response)
{
    return gw_bitmap_valid(request,GW_BITMAP_SIZE,false)&&gw_bitmap_valid(response,GW_BITMAP_SIZE,true)&&
        request[5]==response[5]&&!memcmp(request+8,response+8,60);
}
static inline bool gw_ack_matches(const uint8_t *ack,const uint8_t *request,uint32_t id)
{
    return gw_check(ack,GW_ACK_SIZE,"CGAK",GW_ACK_SIZE)&&
        csi_clock_read_u64(ack+4)==csi_clock_read_u64(request+8)&&
        csi_clock_read_u32(ack+12)==csi_clock_read_u32(request+16)&&
        csi_clock_read_u32(ack+16)==csi_clock_read_u32(request+20)&&
        !memcmp(ack+24,request+24,6)&&csi_clock_read_u32(ack+20)==id;
}
static inline bool gw_bitmap_reply(const uint8_t *request,const uint8_t *cache,unsigned count,uint8_t *response)
{
    if(!gw_bitmap_valid(request,GW_BITMAP_SIZE,false)||count>128||(!cache&&count))return false;
    memcpy(response,request,GW_BITMAP_SIZE);memcpy(response,"CGPB",4);
    for(unsigned i=0;i<response[5];++i){
        uint32_t id=csi_clock_read_u32(response+36+4*i);
        for(unsigned j=0;j<count;++j)if(gw_ack_matches(cache+j*GW_ACK_SIZE,request,id)){response[6]|=1U<<i;break;}
    }
    gw_crc(response,GW_BITMAP_SIZE);return true;
}
#endif
