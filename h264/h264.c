/*
Copyright (c) 2012, Broadcom Europe Ltd
All rights reserved.
Copyright (c) 2018, Hsun-Wei Cho

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
* Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.
* Neither the name of the copyright holder nor the
names of its contributors may be used to endorse or promote products
derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

// Video deocode demo using OpenMAX IL though the ilcient helper library
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <sys/stat.h>
#include <unistd.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>

#include <sys/socket.h>
#include <arpa/inet.h>

#include "bcm_host.h"
#include "ilclient.h"
#include "audio.h"

#define DBG_PRINT_ENABLED 0
#include "debug_print.h"

typedef struct srtppacket {
    uint8_t buf[2048];
    int32_t recvlen;
    int32_t seqnum;
    struct srtppacket* next;
} rtppacket;

atomic_int numofnode;
int32_t audiodest = 0;
int32_t idrsockport = -1;
char* sinkip = "192.168.173.1";

static bool largers (int32_t a, int32_t b);
static bool largers (int32_t a, int32_t b)
{
    bool ret = false;
    if (abs (a - b) < 32768) {
        ret = (a > b);
    } else if ((a - b) <= -32768) {
        ret = true;
    } else {
        /* empty */
    }
    return ret;
}

#define INLINE static inline
#define STATIC static

INLINE void advance_packet (rtppacket** beg);
INLINE void advance_packet (rtppacket** beg)
{
    rtppacket* nexttemp = (*beg)->next;
    free ((*beg));
    (*beg) = nexttemp;
}


INLINE rtppacket* allocate_new_packet (void);
INLINE rtppacket* allocate_new_packet (void) {
    rtppacket* p1 = (rtppacket*)calloc (1, sizeof (rtppacket));
    p1->seqnum = -1;
    return p1;
}


INLINE bool newpesstart (uint8_t* buffer, int32_t shift);
INLINE bool newpesstart (uint8_t* buffer, int32_t shift)
{
    uint32_t* buffer1 = (uint32_t*)(buffer+shift);
    bool start = ((*buffer1) & 0xFFFFFFu) == 0x010000u;
    //bool start = ((buffer[shift] == 0u) && (buffer[shift + 1] == 0u) && (buffer[shift + 2] == 1u));
    return start;
}

INLINE void create_new_audio_renderer (COMPONENT_T** audio_render, ILCLIENT_T* client, COMPONENT_T** list);
INLINE void create_new_audio_renderer (COMPONENT_T** audio_render, ILCLIENT_T* client, COMPONENT_T** list)
{
    if (audioplay_create (client, audio_render, list, 4) != 0) {
        DBG_PRINTF_ERROR ("create error\n");
    }
    /*if (audiodest == 0) {*/
        (void)audioplay_set_dest (*audio_render, "hdmi");
    /*} else if (audiodest == 1) {
        (void)audioplay_set_dest (*audio_render, "local");
    } else {
        (void)audioplay_set_dest (*audio_render, "alsa");
    }*/
}


INLINE int32_t get_numofts (rtppacket* p1);
INLINE int32_t get_numofts (rtppacket* p1) {
    int32_t numofts = (p1->recvlen - 12) / 188;
    return numofts;
}

INLINE void insert_into_list (rtppacket** head, rtppacket** p1);
INLINE void insert_into_list (rtppacket** head, rtppacket** p1) {
    rtppacket* currentp = *head;
    rtppacket* prevp = NULL;
    while (currentp != NULL) {
        if (largers (currentp->seqnum, (*p1)->seqnum)) {
            if (prevp == NULL) {
                /* insert p1 into beginning */
                *head = *p1;
            } else {
    	    /* insert p1 between pervp and currentp */
                prevp->next = *p1;
            }
            (*p1)->next = currentp;
            break;
        } else {
    	    /* advance search by 1 */
            prevp = currentp;
            currentp = currentp->next;
        }
    }
    if ((currentp == NULL)) {
        /* append to end */
        prevp->next = *p1;
    }
}

INLINE int16_t extract_pid (uint8_t* buffer);
INLINE int16_t extract_pid (uint8_t* buffer) {
    int16_t pid = ((((uint16_t*)(buffer+1))[0]) & 0xFF1Fu);
    return pid;
}

INLINE int32_t extract_cc (uint8_t* buffer);
INLINE int32_t extract_cc (uint8_t* buffer) {
    int32_t cc = buffer[3] & 0x0Fu;
    return cc;
}

INLINE int32_t extract_ad (uint8_t* buffer);
INLINE int32_t extract_ad (uint8_t* buffer) {
    int32_t ad = 3u & (buffer[3] >> 4u);
    return ad;
}

INLINE int32_t extract_shift (uint8_t* buffer,int32_t ad);
INLINE int32_t extract_shift (uint8_t* buffer,int32_t ad) {
    int32_t adlen = buffer[4];
    int32_t shift = (ad == 1) ? 4 : (adlen + 5);
    return shift;
}

INLINE void receive_data (rtppacket* p1, int32_t fd);
INLINE void receive_data (rtppacket* p1, int32_t fd) {
    struct sockaddr_in sourceaddr;
    socklen_t addrlen = sizeof (sourceaddr);
    p1->recvlen = recvfrom (fd, p1->buf, 2048, 0, (struct sockaddr*)&sourceaddr, &addrlen);
    if(p1->recvlen>=0) {
        p1->seqnum = (p1->buf[2] << 8) + p1->buf[3];
    }
}


static void sendtodecoder (COMPONENT_T** list, TUNNEL_T* tunnel, OMX_BUFFERHEADERTYPE** buf, rtppacket** beg, rtppacket* scan, int* port_settings_changed, int* first);

static void sendtodecoder (COMPONENT_T** list, TUNNEL_T* tunnel, OMX_BUFFERHEADERTYPE** buf, rtppacket** beg, rtppacket* scan, int* port_settings_changed, int* first)
{
    bool loop = true;
    while (loop) {
        *buf = ilclient_get_input_buffer (list[0], 130, 1);
        if (*buf != NULL) {
            uint8_t* dest = (*buf)->pBuffer;
            int32_t data_len = 0;
            do {
                uint8_t* buffer = (*beg)->buf + 12u;
                for (int32_t i = 0; i < get_numofts((*beg)); i++) {

                    int32_t pid = extract_pid(buffer);
                    int32_t ad = extract_ad(buffer);
                    int32_t shift = extract_shift(buffer,ad);
		    uint32_t bytes_to_copy = 188 - shift;
		    buffer += shift;
                    if ((pid == 0x1110) && ((ad & 1) == 1)) {
                        (void)memcpy (dest, buffer, bytes_to_copy);
			dest += bytes_to_copy;
                        data_len += bytes_to_copy;
                    }

	       	    buffer += bytes_to_copy;
                }
                advance_packet(beg);
                if ((*beg) == scan) {
                    loop = false;
                }
            } while ((loop) && (((*buf)->nAllocLen - data_len) >= 1500));
            if (((*port_settings_changed) == 0) &&
                    (((data_len > 0) && ilclient_remove_event (list[0], OMX_EventPortSettingsChanged, 131, 0, 0, 1) == 0) ||
                     ((data_len == 0) && ilclient_wait_for_event (list[0], OMX_EventPortSettingsChanged, 131, 0, 0, 1, ILCLIENT_EVENT_ERROR | ILCLIENT_PARAMETER_CHANGED, 10000) == 0))) {
                *port_settings_changed = 1;
                if (ilclient_setup_tunnel (tunnel, 0, 0) == 0) {
                    ilclient_change_component_state (list[3], OMX_StateExecuting);
                    // now setup tunnel to video_render
                    if (ilclient_setup_tunnel (tunnel + 1, 0, 1000) == 0) {
                        ilclient_change_component_state (list[1], OMX_StateExecuting);
                    } else {
                        return;
                    }
                } else {
                    return;
                }
            }
            (*buf)->nFilledLen = data_len;
            (*buf)->nOffset = 0;

            if (!loop) {
                const uint8_t sidedata[14] = { 0xea, 0x00, 0x00, 0x00, 0x01, 0xce, 0x8c, 0x4d, 0x9d, 0x10, 0x8e, 0x25, 0xe9, 0xfe };
                (void)memcpy (dest, sidedata, 14);
		dest += 14;
                data_len += 14;
                (*buf)->nFlags |= OMX_BUFFERFLAG_ENDOFFRAME;
            }
            if ((*first) != 0) {
                (*buf)->nFlags |= OMX_BUFFERFLAG_STARTTIME;
                *first = 0;
            } else {
                (*buf)->nFlags |= OMX_BUFFERFLAG_TIME_UNKNOWN;
            }
            if (OMX_EmptyThisBuffer (ILC_GET_HANDLE (list[0]), (*buf)) != OMX_ErrorNone) {
		loop = false;
            }
        } else {
            loop = false;
        }
    }
    return;
}

static void* addnullpacket (rtppacket* beg)
{
    int32_t fd = socket (AF_INET, SOCK_DGRAM, 0);
    if (fd >= 0) {
        struct sockaddr_in addr1 = {.sin_family = AF_INET, .sin_addr.s_addr = inet_addr (sinkip), .sin_port = htons (1028)};
        socklen_t addrlen = sizeof (addr1);

        struct timeval tv = {.tv_sec = 10};
        if (setsockopt (fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof (tv)) < 0) {
            perror ("cannot set timeout\n");
            return 0;
        } else if (bind (fd, (struct sockaddr*)&addr1, sizeof (addr1)) < 0) {
            perror ("bind failed");
            return 0;
        }
        struct sockaddr_in addr2 = {.sin_family = AF_INET,.sin_addr.s_addr = htonl (INADDR_LOOPBACK)};
        int32_t fd2 = 0;
        if (idrsockport > 0) {
            fd2 = socket (AF_INET, SOCK_DGRAM, 0);
            if (fd2 >= 0) {
                addr2.sin_port = htons (idrsockport);
            } else {
                perror ("cannot create socket\n");
                return 0;
            }
        }

        do {
	    receive_data(beg,fd);
        } while (beg->recvlen <= 0);

        bool hold = false;
        int32_t numofpacket = 1;

        rtppacket* head = beg;
        int32_t osn = head->seqnum;

        rtppacket* oldhead = NULL;

        rtppacket* p1 = allocate_new_packet();

        do {
            receive_data(p1,fd);
            if (p1->recvlen > 0) {
                if (largers (osn, p1->seqnum)) {
                    DBG_PRINTF_WARNING ("drop:%d\n", p1->seqnum);
		    /* goto next iteration */
                } else {
                    if (numofpacket == 0) {
                        head = p1;
                    } else {
			insert_into_list(&head,&p1);
                    }
                    numofpacket++;
                    if (osn == head->seqnum) {
                        hold = false;
                    } else if (numofpacket > 14) {
                        hold = false;
                        osn = head->seqnum;
                    } else if ((idrsockport > 0) && (numofpacket == 12)) {
                        const char topython[] = "send idr";
                        if (sendto (fd2, topython, sizeof (topython), 0, (struct sockaddr*)&addr2, addrlen) < 0) {
                            perror ("sendto error");
                        }
                        DBG_PRINTF_TRACE ("idr:%d\n", numofpacket);
                    }
                    if ((numofpacket > 0) && (osn == head->seqnum) && (oldhead != NULL)) {
                        oldhead->next = head;
                    }
                    while ((numofpacket > 0) && (!hold)) {
                        if (osn == head->seqnum) {
                            osn = 0xFFFF & (osn + 1);
                            oldhead = head;
                            head = head->next;
                            numofpacket--;
                            atomic_fetch_add (&numofnode, 1);
                        } else {
                            hold = true;
                        }
                    }
		    /* allocate packet for next iteration */
		    p1 = allocate_new_packet();
                }
	    }
        } while (p1->recvlen>=0);

	if (p1->recvlen<0) {
            const char topython[] = "recv timeout";
            if (sendto (fd2, topython, sizeof (topython), 0, (struct sockaddr*)&addr2, addrlen) < 0) {
                perror ("recv timeout");
            }
	}
    } else {
        perror ("cannot create socket\n");
    }
    return 0;
}


static int32_t video_decode_test (rtppacket* beg)
{
    int32_t status = 0;
    ILCLIENT_T* client = ilclient_init();
    if (client == NULL) {
        status = -3;
    } else if (OMX_Init() != OMX_ErrorNone) {
        ilclient_destroy (client);
        status = -4;
    } else {
        // create video_decode
        COMPONENT_T* list[5] = {0};
        if (ilclient_create_component (client, &list[0], "video_decode", ILCLIENT_DISABLE_ALL_PORTS | ILCLIENT_ENABLE_INPUT_BUFFERS) != 0) {
            status = -14;
        }
        // create video_render
        if ((status == 0) && (ilclient_create_component (client, &list[1], "video_render", ILCLIENT_DISABLE_ALL_PORTS) != 0)) {
            status = -14;
        }
        // create clock
        if ((status == 0) && (ilclient_create_component (client, &list[2], "clock", ILCLIENT_DISABLE_ALL_PORTS) != 0)) {
            status = -14;
        }
        OMX_TIME_CONFIG_CLOCKSTATETYPE cstate = {.nSize = sizeof(cstate), .nVersion.nVersion = OMX_VERSION, .eState = OMX_TIME_ClockStateWaitingForStartTime, .nWaitMask = 1};
        if ((list[2] != NULL) && (OMX_SetParameter (ILC_GET_HANDLE (list[2]), OMX_IndexConfigTimeClockState, &cstate) != OMX_ErrorNone)) {
            status = -13;
        }
        // create video_scheduler
        if ((status == 0) && (ilclient_create_component (client, &list[3], "video_scheduler", ILCLIENT_DISABLE_ALL_PORTS) != 0)) {
            status = -14;
        }
        COMPONENT_T* audio_render = NULL;
        create_new_audio_renderer (&audio_render, client, list);
        TUNNEL_T tunnel[4] = {0};
        set_tunnel (tunnel, list[0], 131, list[3], 10);
        set_tunnel (tunnel + 1, list[3], 11, list[1], 90);
        set_tunnel (tunnel + 2, list[2], 80, list[3], 12);
        // setup clock tunnel first
        if ((status == 0) && (ilclient_setup_tunnel (tunnel + 2, 0, 0) != 0)) {
            status = -15;
        } else {
            ilclient_change_component_state (list[2], OMX_StateExecuting);
        }
        if (status == 0) {
            ilclient_change_component_state (list[0], OMX_StateIdle);
        }
        OMX_VIDEO_PARAM_PORTFORMATTYPE format = {.nSize = sizeof (OMX_VIDEO_PARAM_PORTFORMATTYPE), .nVersion.nVersion = OMX_VERSION, .nPortIndex = 130, .eCompressionFormat = OMX_VIDEO_CodingAVC};

        if ((status == 0) && (OMX_SetParameter (ILC_GET_HANDLE (list[0]), OMX_IndexParamVideoPortFormat, &format) == OMX_ErrorNone) && (ilclient_enable_port_buffers (list[0], 130, NULL, NULL, NULL) == 0)) {
            OMX_BUFFERHEADERTYPE* buf = NULL;
            int32_t port_settings_changed = 0;
            ilclient_change_component_state (list[0], OMX_StateExecuting);
            int32_t oldcc = 0;
            int32_t peserror = 1;
            int32_t first = 1;
            rtppacket* scan = beg;
            do {
                int32_t non = atomic_load (&numofnode);
                if (non < 2) {
		    /* need at least two nodes, so one can be consumed */
                    usleep (1);
                } else {
		    /* consume one node */
		    uint8_t* buffer = scan->buf + 12u;
                    for (int32_t i = 0; i < get_numofts(scan); i++) {
                        if (buffer[0] == 0x47u) {
                            int32_t ad = extract_ad(buffer);
                            int32_t shift = extract_shift(buffer,ad);
                            int32_t pid = extract_pid(buffer);
                            int32_t cc = extract_cc(buffer);

                            if (pid == 0x1110) {
                                if (cc != oldcc) {
                                    DBG_PRINTF_TRACE ("oldcc %d cc %d\n", oldcc, cc);
                                    peserror = 1;
                                }
                                oldcc = 0xF & (cc + 1);

                                if ((ad & 1) != 0) {
                                    if (newpesstart (buffer, shift)) {
                                        if (peserror == 0) {
                                            sendtodecoder (list, tunnel, &buf, &beg, scan, &port_settings_changed, &first);
                                        } else {
                                            first = 1;
                                            while (beg != scan) {
                                                advance_packet (&beg);
                                            }
                                        }
                                        peserror = 0;
                                    }
                                }
                            }
			    if (pid == 0x0011) {
                                if ((ad & 1) != 0) {
                                    if (newpesstart (buffer, shift)) {
                                        shift += 20;
                                    }
                                    if (audioplay_play_buffer (audio_render, buffer + shift, 188 - shift) < 0) {
                                        DBG_PRINTF_ERROR ("sound error\n");
                                    }
                                }
                            }
                        }
                        buffer += 188u;
                    }
                    atomic_fetch_sub (&numofnode, 1);
                    scan = scan->next;
                }
            } while (true);
            if (buf != NULL) {
                buf->nFilledLen = 0;
                buf->nFlags = OMX_BUFFERFLAG_TIME_UNKNOWN | OMX_BUFFERFLAG_EOS;
            }
            if (OMX_EmptyThisBuffer (ILC_GET_HANDLE (list[0]), buf) != OMX_ErrorNone) {
                status = -20;
            }
            ilclient_wait_for_event (list[1], OMX_EventBufferFlag, 90, 0, OMX_BUFFERFLAG_EOS, 0, ILCLIENT_BUFFER_FLAG_EOS, -1); // wait for EOS from render
            ilclient_flush_tunnels (tunnel, 0); // need to flush the renderer to allow video_decode to disable its input port
        }
        ilclient_disable_tunnel (tunnel);
        ilclient_disable_tunnel (tunnel + 1);
        ilclient_disable_tunnel (tunnel + 2);
        ilclient_disable_port_buffers (list[0], 130, NULL, NULL, NULL);
        ilclient_teardown_tunnels (tunnel);
        ilclient_state_transition (list, OMX_StateIdle);
        ilclient_state_transition (list, OMX_StateLoaded);
        ilclient_cleanup_components (list);
        OMX_Deinit();
        ilclient_destroy (client);
    }
    return status;
}

int main (int argc, char** argv)
{
    if (argc > 1) {
        idrsockport = atoi (argv[1]);
        DBG_PRINTF_DEBUG ("idrport:%d\n", idrsockport);
    }
    if (argc > 2) {
        audiodest = atoi (argv[2]);
        DBG_PRINTF_DEBUG ("audiodest:%d\n", audiodest);
    }
    if (argc > 3) {
        sinkip = argv[3];
        DBG_PRINTF_DEBUG ("sinkip:%s\n", sinkip);
    }
    atomic_store (&numofnode, 0);
    pthread_t npthread;
    pthread_t dthread;
    rtppacket* beg = allocate_new_packet();
    
    bcm_host_init();
    int retval = 0;
    if (pthread_create (&npthread, NULL, addnullpacket, beg) != 0) {
        retval = 1;
    }
    if ((retval == 0) && (pthread_create (&dthread, NULL, video_decode_test, beg) != 0)) {
        retval = 1;
    }
    if ((retval == 0) && (pthread_join (npthread, NULL) != 0)) {
        retval = 1;
    }
    if ((retval == 0) && (pthread_join (dthread, NULL) != 0)) {
        retval = 1;
    }
    return retval;
}


