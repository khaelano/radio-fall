#ifndef CSI_WIRELESS_LINK_PROTOCOL_H
#define CSI_WIRELESS_LINK_PROTOCOL_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* Connectionless BLE only; CSI envelopes never enter this stream. */
#define WL_PAYLOAD 1280
#define WL_LOGICAL 4096
/* One complete periodic HCI update, including AD/header/authentication. */
#define WL_PERIODIC_PAYLOAD 190
#define WL_WINDOW 4
#define WL_HEADER 37
#define WL_TAG 16
_Static_assert(WL_HEADER+WL_PERIODIC_PAYLOAD+WL_TAG+4<=251,"periodic data must fit one HCI update");
#define WL_PACKET (WL_HEADER+WL_PAYLOAD+WL_TAG)
#define WL_EMPTY UINT32_MAX
#define WL_PAIR_SIZE 48
#define WL_USB_REQUEST 26
#define WL_USB_RESPONSE 27
#define WL_USB_PAIR 28
#define WL_USB_PAIR_ACK 29
static inline uint16_t wl_u16(const uint8_t *p){return (uint16_t)p[0]<<8|p[1];}
static inline uint32_t wl_u32(const uint8_t *p){return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static inline uint64_t wl_u64(const uint8_t *p){return (uint64_t)wl_u32(p)<<32|wl_u32(p+4);}
static inline void wl_w16(uint8_t *p,uint16_t v){p[0]=v>>8;p[1]=v;}
static inline void wl_w32(uint8_t *p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static inline void wl_w64(uint8_t *p,uint64_t v){wl_w32(p,v>>32);wl_w32(p+4,v);}
typedef struct {bool used;uint32_t sequence;uint16_t size;uint64_t created,sent;uint8_t data[WL_PAYLOAD];} wl_slot_t;
typedef struct {uint32_t next_tx,next_rx,acknowledged;wl_slot_t tx[WL_WINDOW],rx[WL_WINDOW];} wl_stream_t;
typedef void (*wl_emit_t)(uint8_t,const uint8_t *,size_t,void *);
typedef bool (*wl_block_t)(const uint8_t *,size_t,void *);
typedef bool (*wl_mac_t)(const uint8_t *,size_t,uint8_t [32]);
static inline bool wl_epoch_valid(uint32_t known,uint32_t current,uint64_t nonce,uint32_t remote,uint64_t remote_nonce)
{
    if(!remote||!remote_nonce||remote<known)return false;
    if(remote==current&&remote_nonce!=nonce)return false;
    if(remote==known&&current&&remote!=current)return false;
    return true;
}
static inline bool wl_packet_valid(const uint8_t *p,size_t n,uint8_t local_role,wl_mac_t mac)
{
    if(n<WL_HEADER+WL_TAG||n>WL_PACKET||memcmp(p,"CWL2",4)||p[4]!=2||p[5]!=(local_role^1)||wl_u16(p+35)!=n-WL_HEADER-WL_TAG)return false;
    uint8_t digest[32],different=0;
    if(!mac(p,n-WL_TAG,digest))return false;
    for(unsigned i=0;i<WL_TAG;++i)different|=digest[i]^p[n-WL_TAG+i];
    return different==0;
}
/* Small self-contained LZ blocks: literals 1..128, matches 3..130 at distance
 * 1..256. No dictionary state crosses packet or boot boundaries. */
static inline size_t wl_compress(const uint8_t *p,size_t n,uint8_t *out,size_t capacity)
{
    if(!n||n>WL_LOGICAL)return 0;
    uint16_t recent[256];for(unsigned i=0;i<256;++i)recent[i]=UINT16_MAX;
    size_t pos=0,literal=0,used=0;
    while(pos<n){
        size_t match=0,distance=0;
        if(n-pos>=3){unsigned hash=(p[pos]*31U+p[pos+1]*17U+p[pos+2])&255;
            uint16_t previous=recent[hash];recent[hash]=pos;
            if(previous!=UINT16_MAX&&pos>previous&&pos-previous<=256){
                distance=pos-previous;
                while(match<130&&pos+match<n&&p[previous+match]==p[pos+match])++match;
            }
        }
        if(match>=3){
            if(pos>literal){size_t count=pos-literal;if(used+count+1>capacity)return 0;out[used++]=count-1;memcpy(out+used,p+literal,count);used+=count;}
            if(used+2>capacity)return 0;
            out[used++]=0x80|(match-3);out[used++]=distance-1;pos+=match;literal=pos;
        }else{
            ++pos;if(pos-literal==128||pos==n){size_t count=pos-literal;if(used+count+1>capacity)return 0;out[used++]=count-1;memcpy(out+used,p+literal,count);used+=count;literal=pos;}
        }
    }
    return used;
}
static inline size_t wl_decompress(const uint8_t *p,size_t n,uint8_t *out,size_t capacity)
{
    size_t used=0;
    while(n){unsigned code=*p++;--n;
        if(code&0x80){size_t count=(code&127)+3;if(!n)return 0;size_t distance=(size_t)(*p++)+1;--n;
            if(distance>used||count>capacity-used)return 0;
            for(size_t i=0;i<count;++i)out[used+i]=out[used-distance+i];
            used+=count;
        }else{size_t count=code+1;if(count>n||count>capacity-used)return 0;memcpy(out+used,p,count);used+=count;p+=count;n-=count;}
    }
    return used;
}
static inline bool wl_frames_valid(const uint8_t *p,size_t n)
{
    if(!n||n>WL_LOGICAL)return false;
    while(n){if(n<3)return false;size_t size=wl_u16(p+1);if(!p[0]||size>n-3||size+3>=WL_PAYLOAD)return false;p+=size+3;n-=size+3;}
    return true;
}
/* Select a complete-frame prefix; oversize logical batches must not force a
 * raw-only fallback. Search remains bounded and never consumes an unencoded byte. */
static inline size_t wl_encode_frames(const uint8_t *p,size_t n,uint8_t *out,size_t capacity,size_t *consumed)
{
    *consumed=0;
    if(capacity<2||!wl_frames_valid(p,n))return 0;
    size_t raw=0;
    while(raw<n){size_t frame=wl_u16(p+raw+1)+3;if(frame>capacity-1-raw)break;raw+=frame;}
    if(!raw)return 0;
    size_t best=raw,low=raw,high=n;
    size_t packed=wl_compress(p,n,out+1,capacity-1);
    if(packed&&packed<n){out[0]=1;*consumed=n;return packed+1;}
    while(low<high){
        size_t target=low+(high-low+1)/2,chosen=low;
        while(chosen<n&&chosen<target)chosen+=wl_u16(p+chosen+1)+3;
        if(chosen>=high)break;
        packed=wl_compress(p,chosen,out+1,capacity-1);
        if(packed&&packed<chosen){best=chosen;low=chosen;}
        else high=chosen;
    }
    packed=wl_compress(p,best,out+1,capacity-1);
    if(packed&&packed<best){out[0]=1;*consumed=best;return packed+1;}
    out[0]=0;memcpy(out+1,p,raw);*consumed=raw;return raw+1;
}
static inline wl_slot_t *wl_stream_add(wl_stream_t *s,const uint8_t *p,size_t n,uint64_t now)
{
    if(!n||n>WL_PAYLOAD||s->next_tx>=UINT32_MAX-WL_WINDOW||s->next_tx-s->acknowledged>=WL_WINDOW)return NULL;
    for(unsigned i=0;i<WL_WINDOW;++i)if(!s->tx[i].used){
        wl_slot_t *v=&s->tx[i];*v=(wl_slot_t){.used=true,.sequence=s->next_tx++,.size=n,.created=now};memcpy(v->data,p,n);return v;
    }
    return NULL;
}
static inline bool wl_stream_ack(wl_stream_t *s,uint32_t base,uint8_t mask)
{
    if(base>s->next_tx||mask&0xf0)return false;
    if(base<s->acknowledged)return true; /* An older advertisement may repeat an ACK. */
    for(unsigned bit=0;bit<WL_WINDOW;++bit)if((mask&(1U<<bit))&&((uint64_t)base+bit>=s->next_tx))return false;
    s->acknowledged=base;
    for(unsigned i=0;i<WL_WINDOW;++i){wl_slot_t *v=&s->tx[i];
        if(v->used&&(v->sequence<base||(v->sequence-base<WL_WINDOW&&(mask&(1U<<(v->sequence-base))))))v->used=false;
    }
    return true;
}
static inline uint8_t wl_stream_mask(const wl_stream_t *s)
{
    uint8_t mask=0;for(unsigned i=0;i<WL_WINDOW;++i)if(s->rx[i].used&&s->rx[i].sequence>=s->next_rx&&s->rx[i].sequence-s->next_rx<WL_WINDOW)mask|=1U<<(s->rx[i].sequence-s->next_rx);return mask;
}
static inline bool wl_stream_receive(wl_stream_t *s,uint32_t seq,const uint8_t *p,size_t n,wl_block_t emit,void *context)
{
    if(seq==WL_EMPTY||!n||n>WL_PAYLOAD||s->next_rx>=UINT32_MAX-WL_WINDOW)return false;
    if(seq<s->next_rx)return true; /* Retransmission: acknowledge without replay. */
    if((uint64_t)seq>=((uint64_t)s->next_rx+WL_WINDOW))return false;
    wl_slot_t *v=&s->rx[seq%WL_WINDOW];
    if(v->used)return v->sequence==seq&&v->size==n&&!memcmp(v->data,p,n);
    *v=(wl_slot_t){.used=true,.sequence=seq,.size=n};memcpy(v->data,p,n);
    while((v=&s->rx[s->next_rx%WL_WINDOW])->used&&v->sequence==s->next_rx){
        if(!emit(v->data,v->size,context))return false;
        v->used=false;++s->next_rx;
    }
    return true;
}
/* Individual AD elements have one-byte lengths even with extended advertising. */
static inline size_t wl_ad_encode(const uint8_t *p,size_t n,uint8_t *out,size_t capacity)
{
    if(!n||n>WL_PACKET)return 0;
    size_t used=0;
    while(n){size_t chunk=n>251?251:n;if(used+chunk+4>capacity)return 0;
        out[used++]=chunk+3;out[used++]=0xff;out[used++]=0xff;out[used++]=0xff;memcpy(out+used,p,chunk);used+=chunk;p+=chunk;n-=chunk;
    }
    return used;
}
static inline size_t wl_ad_decode(const uint8_t *p,size_t n,uint8_t *out,size_t capacity)
{
    size_t used=0;
    while(n){unsigned length=*p++;--n;if(!length||length>n)return 0;
        if(length>=3&&p[0]==0xff&&p[1]==0xff&&p[2]==0xff){size_t chunk=length-3;if(used+chunk>capacity)return 0;memcpy(out+used,p+3,chunk);used+=chunk;}
        p+=length;n-=length;
    }
    return used;
}
#endif
