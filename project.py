#!/usr/bin/env python2
"""
    This software is part of lazycast, a simple wireless display receiver for Raspberry Pi
    Copyright (C) 2020 Hsun-Wei Cho
    Using any part of the code in commercial products is prohibited.
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import socket
from time import sleep
import os
import uuid
import fcntl, os
import errno
import threading
from threading import Thread
import time
import sys
import subprocess
import argparse
from logging import DEBUG, StreamHandler, getLogger
import logging
from contextlib import closing


class Res:
    def __init__(self, id, width, height, refresh, progressive=True, h264level='3.1', h265level='3.1'):
        self.id = id
        self.width = width
        self.height = height
        self.refresh = refresh
        self.progressive = progressive
        self.h264level = h264level
        self.h265level = h265level

    @property
    def score(self):
        return self.width * self.height * self.refresh * (1 + 1 if self.progressive else 0)

    def __repr__(self):
        return "%s(%d,%d,%d,%d,%s)" % (type(self).__name__, self.id, self.width, self.height, self.refresh,
                                       'p' if self.progressive else 'i')

    def __str__(self):
        return 'resolution(%d) %d x %d x %d%s' % (self.id, self.width, self.height, self.refresh,
                                                  'p' if self.progressive else 'i')

    def __eq__(self, other):
        return repr(self) == repr(other)

    def __ne__(self, other):
        return repr(self) != repr(other)

    def __ge__(self, other):
        return self.score >= other.score

    def __gt__(self, other):
        return self.score > other.score

    def __le__(self, other):
        return self.score <= other.score

    def __lt__(self, other):
        return self.score < other.score


class WfdVideoParameters:

    resolutions_cea = [
        Res(0,   640,  480, 60, True),
        Res(1,   720,  480, 60, True),
        Res(2,   720,  480, 60, False),
        Res(3,   720,  480, 50, True),
        Res(4,   720,  576, 50, False),
        Res(5,  1280,  720, 30, True),
        Res(6,  1280,  720, 60, True, '3.2', '4'),
        Res(7,  1280, 1080, 30, True, '4', '4'),
        Res(8,  1920, 1080, 60, True, '4.2', '4.1'),
        Res(9,  1920, 1080, 60, False, '4', '4'),
        Res(10, 1280,  720, 25, True),
        Res(11, 1280,  720, 50, True, '3.2', '4'),
        Res(12, 1920, 1080, 25, True, '3.2', '4'),
        Res(13, 1920, 1080, 50, True, '4.2', '4.1'),
        Res(14, 1920, 1080, 50, False, '3.2', '4'),
        Res(15, 1280,  720, 24, True),
        Res(16, 1920, 1080, 24, True, '3.2', '4'),
        Res(17, 3840, 2160, 30, True, '5.1', '5'),
        Res(18, 3840, 2160, 60, True, '5.1', '5'),
        Res(19, 4096, 2160, 30, True, '5.1', '5'),
        Res(20, 4096, 2160, 60, True, '5.2', '5.1'),
        Res(21, 3840, 2160, 25, True, '5.2', '5.1'),
        Res(22, 3840, 2160, 50, True, '5.2', '5'),
        Res(23, 4096, 2160, 25, True, '5.2', '5'),
        Res(24, 4086, 2160, 50, True, '5.2', '5'),
        Res(25, 4096, 2160, 24, True, '5.2', '5.1'),
        Res(26, 4096, 2160, 24, True, '5.2', '5.1'),
    ]

    resolutions_vesa = [
        Res(0,   800,  600, 30, True, '3.1', '3.1'),
        Res(1,   800,  600, 60, True, '3.2', '4'),
        Res(2,  1024,  768, 30, True, '3.1', '3.1'),
        Res(3,  1024,  768, 60, True, '3.2', '4'),
        Res(4,  1152,  854, 30, True, '3.2', '4'),
        Res(5,  1152,  854, 60, True, '4', '4.1'),
        Res(6,  1280,  768, 30, True, '3.2', '4'),
        Res(7,  1280,  768, 60, True, '4', '4.1'),
        Res(8,  1280,  800, 30, True, '3.2', '4'),
        Res(9,  1280,  800, 60, True, '4', '4.1'),
        Res(10, 1360,  768, 30, True, '3.2', '4'),
        Res(11, 1360,  768, 60, True, '4', '4.1'),
        Res(12, 1366,  768, 30, True, '3.2', '4'),
        Res(13, 1366,  768, 60, True, '4.2', '4.1'),
        Res(14, 1280, 1024, 30, True, '3.2', '4'),
        Res(15, 1280, 1024, 60, True, '4.2', '4.1'),
        Res(16, 1440, 1050, 30, True, '3.2', '4'),
        Res(17, 1440, 1050, 60, True, '4.2', '4.1'),
        Res(18, 1440,  900, 30, True, '3.2', '4'),
        Res(19, 1440,  900, 60, True, '4.2', '4.1'),
        Res(20, 1600,  900, 30, True, '3.2', '4'),
        Res(21, 1600,  900, 60, True, '4.2', '4.1'),
        Res(22, 1600, 1200, 30, True, '4', '5'),
        Res(23, 1600, 1200, 60, True, '4.2', '5.1'),
        Res(24, 1680, 1024, 30, True, '3.2', '4'),
        Res(25, 1680, 1024, 60, True, '4.2', '4.1'),
        Res(26, 1680, 1050, 30, True, '3.2', '4'),
        Res(27, 1680, 1050, 60, True, '4.2', '4.1'),
        Res(28, 1920, 1200, 30, True, '4.2', '5'),
    ]

    resolutions_hh = [
        Res(0, 800, 400, 30),
        Res(1, 800, 480, 60),
        Res(2, 854, 480, 30),
        Res(3, 854, 480, 60),
        Res(4, 864, 480, 30),
        Res(5, 864, 480, 60),
        Res(6, 640, 360, 30),
        Res(7, 640, 360, 60),
        Res(8, 960, 540, 30),
        Res(9, 960, 540, 60),
        Res(10, 848, 480, 30),
        Res(11, 848, 480, 60),
    ]

    def get_video_parameter(self):
        # audio_codec: LPCM:0x01, AAC:0x02, AC3:0x04
        # audio_sampling_frequency: 44.1khz:1, 48khz:2
        # LPCM: 44.1kHz, 16b; 48 kHZ,16b
        # AAC: 48 kHz, 16b, 2 channels; 48kHz,16b, 4 channels, 48 kHz,16b,6 channels
        # AAC 00000001 00  : 2 ch AAC 48kHz
        msg = 'wfd_audio_codecs: LPCM 00000002 00\r\n'
        #msg ='wfd_audio_codecs: AAC 00000001 00\r\n'
        #msg = 'wfd_audio_codecs: AAC 00000001 00, LPCM 00000002 00\r\n'
        
        # wfd_video_formats: <native_resolution: 0x20>, <preferred>, <profile>, <level>,
        #                    <cea>, <vesa>, <hh>, <latency>, <min_slice>, <slice_enc>, <frame skipping support>
        #                    <max_hres>, <max_vres>
        # native: index in CEA support.
        # preferred-display-mode-supported: 0 or 1
        # profile: Constrained High Profile: 0x02, Constraint Baseline Profile: 0x01
        # level: H264 level 3.1: 0x01, 3.2: 0x02, 4.0: 0x04,4.1:0x08, 4.2=0x10
        #   3.2: 720p60,  4.1: FullHD@24, 4.2: FullHD@60
        native = 0x08
        preferred = 0
        profile = 0x02 | 0x01
        level = 0x10

        res_cea_640_480p60   = 1
        res_cea_720_480p60   = 1
        res_cea_720_480i60   = 1
        res_cea_720_576p50   = 1
        res_cea_720_576i50   = 1
        res_cea_1280_720p30  = 1
        res_cea_1280_720p60  = 0
        res_cea_1920_1080p30 = 1
        res_cea_1920_1080p60 = 0 ####
        res_cea_1920_1080i60 = 0
        res_cea_1280_720p25  = 1
        res_cea_1280_720p50  = 1
        res_cea_1920_1080p25 = 1
        res_cea_1920_1080p50 = 0
        res_cea_1920_1080i50 = 0
        res_cea_1280_720p24  = 1
        res_cea_1920_1080p24 = 1
        
        res_vesa_800_600p30   = 0
        res_vesa_800_600p60   = 0
        res_vesa_1024_768p30  = 0
        res_vesa_1024_768p60  = 0
        res_vesa_1152_854p30  = 0
        res_vesa_1152_854p60  = 0
        res_vesa_1280_768p30  = 0
        res_vesa_1280_768p60  = 0
        res_vesa_1280_800p30  = 0
        res_vesa_1280_800p60  = 0
        res_vesa_1360_768p30  = 0
        res_vesa_1360_768p60  = 0
        res_vesa_1366_768p30  = 0
        res_vesa_1366_768p60  = 0
        res_vesa_1280_1024p30 = 0
        res_vesa_1280_1024p60 = 0
        res_vesa_1440_1050p30 = 0
        res_vesa_1440_1050p60 = 0
        res_vesa_1440_900p30  = 0
        res_vesa_1440_900p60  = 0
        res_vesa_1600_900p30  = 0
        res_vesa_1600_900p60  = 0
        res_vesa_1600_1200p30 = 0
        res_vesa_1600_1200p60 = 0
        res_vesa_1680_1024p30 = 0
        res_vesa_1680_1024p60 = 0
        res_vesa_1680_1050p30 = 0
        res_vesa_1680_1050p60 = 0
        res_vesa_1920_1200p30 = 0
        
        res_hh_800_480p30 = 0
        res_hh_800_480p60 = 0
        res_hh_854_480p30 = 0
        res_hh_854_480p60 = 0
        res_hh_864_480p30 = 0
        res_hh_864_480p60 = 0
        res_hh_640_360p30 = 0
        res_hh_640_360p60 = 0
        res_hh_960_540p30 = 0
        res_hh_960_540p60 = 0
        res_hh_848_480p30 = 0
        res_hh_848_480p60 = 0
        
        res_cea = 0
        res_cea = (res_cea<<1) + res_cea_1920_1080p24
        res_cea = (res_cea<<1) + res_cea_1280_720p24
        res_cea = (res_cea<<1) + res_cea_1920_1080i50
        res_cea = (res_cea<<1) + res_cea_1920_1080p50
        res_cea = (res_cea<<1) + res_cea_1920_1080p25
        res_cea = (res_cea<<1) + res_cea_1280_720p50
        res_cea = (res_cea<<1) + res_cea_1280_720p25
        res_cea = (res_cea<<1) + res_cea_1920_1080i60
        res_cea = (res_cea<<1) + res_cea_1920_1080p60
        res_cea = (res_cea<<1) + res_cea_1920_1080p30
        res_cea = (res_cea<<1) + res_cea_1280_720p60
        res_cea = (res_cea<<1) + res_cea_1280_720p30
        res_cea = (res_cea<<1) + res_cea_720_576i50
        res_cea = (res_cea<<1) + res_cea_720_576p50
        res_cea = (res_cea<<1) + res_cea_720_480i60
        res_cea = (res_cea<<1) + res_cea_720_480p60
        res_cea = (res_cea<<1) + res_cea_640_480p60
        
        res_vesa = 0
        res_vesa = (res_vesa<<1) + res_vesa_1920_1200p30
        res_vesa = (res_vesa<<1) + res_vesa_1680_1050p60
        res_vesa = (res_vesa<<1) + res_vesa_1680_1050p30
        res_vesa = (res_vesa<<1) + res_vesa_1680_1024p60
        res_vesa = (res_vesa<<1) + res_vesa_1680_1024p30
        res_vesa = (res_vesa<<1) + res_vesa_1600_1200p60
        res_vesa = (res_vesa<<1) + res_vesa_1600_1200p30
        res_vesa = (res_vesa<<1) + res_vesa_1600_900p60
        res_vesa = (res_vesa<<1) + res_vesa_1600_900p30
        res_vesa = (res_vesa<<1) + res_vesa_1440_900p60
        res_vesa = (res_vesa<<1) + res_vesa_1440_900p30
        res_vesa = (res_vesa<<1) + res_vesa_1440_1050p60
        res_vesa = (res_vesa<<1) + res_vesa_1440_1050p30
        res_vesa = (res_vesa<<1) + res_vesa_1280_1024p60
        res_vesa = (res_vesa<<1) + res_vesa_1280_1024p30
        res_vesa = (res_vesa<<1) + res_vesa_1366_768p60
        res_vesa = (res_vesa<<1) + res_vesa_1366_768p30
        res_vesa = (res_vesa<<1) + res_vesa_1360_768p60
        res_vesa = (res_vesa<<1) + res_vesa_1360_768p30
        res_vesa = (res_vesa<<1) + res_vesa_1280_800p60
        res_vesa = (res_vesa<<1) + res_vesa_1280_800p30
        res_vesa = (res_vesa<<1) + res_vesa_1280_768p60
        res_vesa = (res_vesa<<1) + res_vesa_1280_768p30
        res_vesa = (res_vesa<<1) + res_vesa_1152_854p60
        res_vesa = (res_vesa<<1) + res_vesa_1152_854p30
        res_vesa = (res_vesa<<1) + res_vesa_1024_768p60
        res_vesa = (res_vesa<<1) + res_vesa_1024_768p30
        res_vesa = (res_vesa<<1) + res_vesa_800_600p60
        res_vesa = (res_vesa<<1) + res_vesa_800_600p30
        
        res_hh = 0
        res_hh = (res_hh<<1) + res_hh_848_480p60
        res_hh = (res_hh<<1) + res_hh_848_480p30
        res_hh = (res_hh<<1) + res_hh_960_540p60
        res_hh = (res_hh<<1) + res_hh_960_540p30
        res_hh = (res_hh<<1) + res_hh_640_360p60
        res_hh = (res_hh<<1) + res_hh_640_360p30
        res_hh = (res_hh<<1) + res_hh_864_480p60
        res_hh = (res_hh<<1) + res_hh_864_480p30
        res_hh = (res_hh<<1) + res_hh_854_480p60
        res_hh = (res_hh<<1) + res_hh_854_480p30
        res_hh = (res_hh<<1) + res_hh_800_480p60
        res_hh = (res_hh<<1) + res_hh_800_480p30

        cea = res_cea
        vesa = res_vesa
        handheld = res_hh
        msg += 'wfd_video_formats: {0:02X} {1:02X} {2:02X} {3:02X} {4:08X} {5:08X} {6:08X}' \
               ' 00 0000 0000 00 none none\r\n'.format(native, preferred, profile, level, cea, vesa, handheld)
        msg += 'wfd_3d_video_formats: none\r\n' \
               'wfd_coupled_sink: none\r\n' \
               'wfd_display_edid: none\r\n' \
               'wfd_connector_type: 05\r\n' \
               'wfd_uibc_capability: none\r\n' \
               'wfd_standby_resume_capability: none\r\n' \
               'wfd_content_protection: none\r\n'
        return msg

class Player:
    def __init__(self,sinkip,idrsockport):
        pass
        self.player = None
        self.sinkip = sinkip
        self.idrsockport = idrsockport
    def start(self):
        sound_output_select = 0
        # 0: HDMI sound output
        # 1: 3.5mm audio jack output
        # 2: alsa
        self.player = subprocess.Popen(["./h264/h264.bin",str(self.idrsockport),str(sound_output_select),self.sinkip])
    def stop(self):
        if self.player != None:
            self.player.kill()
            self.player = None

class PiCast:
    def __init__(self, sourceip):
        self.logger = getLogger("PiCast")
        self.watchdog = 0
        self.csnum = 0
        self.player = None

        self.sourceip = sourceip
    def rtsp_response_header(self, cmd=None, url=None, res=None, seq=None, others=None):
        if cmd is not None:
            msg = "{0:s} {1:s} RTSP/1.0".format(cmd, url)
        else:
            msg = "RTSP/1.0"
        if res is not None:
            msg += ' {0:s}\r\nCSeq: {1:d}\r\n'.format(res, seq)
        else:
            msg += '\r\nCSeq: {0:d}\r\n'.format(seq)
        if others is not None:
            for k,v in others:
                msg += '{}: {}\r\n'.format(k,v)
        msg += '\r\n'
        return msg
    def run(self):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            server_address = (self.sourceip, 7236)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.connect(server_address)
            except socket.error, e:
                return
            with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as idrsock:
                idrsock_address = ('127.0.0.1', 0)
                idrsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                idrsock.bind(idrsock_address)
                addr, idrsockport = idrsock.getsockname()
                self.player = Player(sock.getsockname()[0],idrsockport)
                self.negotiate(sock)
                self.player.start()
                fcntl.fcntl(sock, fcntl.F_SETFL, os.O_NONBLOCK)
                fcntl.fcntl(idrsock, fcntl.F_SETFL, os.O_NONBLOCK)
                self.rtpsrv(sock, idrsock)

    def m1(self, sock):
        logger = getLogger("PiCast.m1")
        data = (sock.recv(1000))
        logger.debug("<-{}".format(data))
        s_data = self.rtsp_response_header(seq=1, res="200 OK", others=[("Public", "org.wfa.wfd1.0, SET_PARAMETER, GET_PARAMETER")])
        logger.debug("->{}".format(s_data))
        sock.sendall(s_data)
    def m2(self, sock):
        logger = getLogger("PiCast.m2")
        s_data = self.rtsp_response_header(seq=1, cmd="OPTIONS", url="*", others=[("Require", "org.wfa.wfd1.0")])
        logger.debug("<-{}".format(s_data))
        sock.sendall(s_data)
        data = (sock.recv(1000))
        logger.debug("->{}".format(data))
    def m3(self, sock):
        logger = getLogger("PiCast.m3")
        data=(sock.recv(1000))
        logger.debug("->{}".format(data))
        
        msg = 'wfd_client_rtp_ports: RTP/AVP/UDP;unicast 1028 0 mode=play\r\n'
        msg = msg + WfdVideoParameters().get_video_parameter() 
        
        m3resp = self.rtsp_response_header(seq=2, res="200 OK", others=[("Content-Type", "text/parameters"),("Content-Length",len(msg))])+msg
        sock.sendall(m3resp)
        logger.debug("<-{}".format(m3resp))
    def m4(self, sock):
        logger = getLogger("PiCast.m4")
        data=(sock.recv(1000))
        logger.debug("->{}".format(data))
        
        s_data = self.rtsp_response_header(seq=3, res="200 OK")
        sock.sendall(s_data)
        logger.debug("<-{}".format(s_data))
    def m5(self, sock):
        logger = getLogger("PiCast.m5")
        data=(sock.recv(1000))
        logger.debug("->{}".format(data))
        
        s_data = self.rtsp_response_header(seq=4, res="200 OK")
        sock.sendall(s_data)
        logger.debug("<-{}".format(s_data))
    def m6(self, sock):
        logger = getLogger("PiCast.m6")
        m6req = self.rtsp_response_header(seq=5, cmd="SETUP", url="rtsp://{0:s}/wfd1.0/streamid=0".format(self.sourceip),others=[("Transport","RTP/AVP/UDP;unicast;client_port={0:d}".format(1028))])
        logger.debug("<-{}".format(m6req))
        sock.sendall(m6req)
        
        data= sock.recv(1000)
        logger.debug("->{}".format(data))
        
        paralist=data.split(';')
        serverport=[x for x in paralist if 'server_port=' in x]
        serverport=serverport[-1]
        serverport=serverport[12:17]
        logger.debug("server port {}".format(serverport))
        
        paralist=data.split()
        position=paralist.index('Session:')+1
        sessionid=paralist[position]
        return sessionid
    def m7(self, sock, sessionid):
        logger = getLogger("PiCast.m7")
        m7req = self.rtsp_response_header(seq=6, cmd="PLAY", url="rtsp://{0:s}/wfd1.0/streamid=0".format(self.sourceip),others=[("Session",sessionid)])
        sock.sendall(m7req)
        logger.debug("<-{}".format(m7req))
        
        data= sock.recv(1000)
        logger.debug("->{}".format(data))
    def negotiate(self, conn):
        logger = getLogger("PiCast.daemon")
        logger.debug("---- Start negotiation ----")
        self.m1(conn)
        self.m2(conn)
        self.m3(conn)
        self.m4(conn)
        self.m5(conn)
        sessionid = self.m6(conn)
        self.m7(conn, sessionid)
        logger.debug("---- Negotiation successful ----")
    def handle_rcv_err(self, e, csnum, sock, idrsock):
        logger = getLogger("PiCast.daemon.error")
        err = e.args[0]
        if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
          try:
            datafromc = idrsock.recv(1000)
          except socket.error, e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
              processrunning = os.popen('ps au').read()
              if 'h264.bin' not in processrunning:
                self.player.start()
                sleep(0.01)
              else:
                self.watchdog += 1
                if self.watchdog == 70/0.01:
                  self.player.stop()
                  sleep(1)
            else:
              logger.debug("socket error.")
          else:
            csnum = csnum + 1
            msg = 'wfd_idr_request\r\n'
            idrreq = self.rtsp_response_header(seq=csnum, cmd="SET_PARAMETER", url="rtsp://localhost/wfd1.0", others=[("Content-Length",len(msg)),("Content-Type","text/parameters")])+msg
            sock.sendall(idrreq)
            logger.debug("idreq: {}".format(idrreq))
        else:
          logger.debug("Exit because of socket error")
        return csnum

    def rtpsrv(self, sock, idrsock):
        logger = getLogger("PiCast.rtpsrv")
        csnum = 102
        self.watchdog = 0
        while True:
          try:
            data = sock.recv(1000)
          except socket.error, e:
            csnum = self.handle_rcv_err(e, csnum, sock, idrsock)
          else:
            logger.debug("->{}".format(data))
            self.watchdog = 0
            if len(data)==0 or 'wfd_trigger_method: TEARDOWN' in data:
              self.player.stop()
              sleep(1)
              break
            elif 'wfd_video_formats' in data:
              logger.info("start player")
              self.player.start()
            messagelist=data.split('\r\n\r\n')
            singlemessagelist=[x for x in messagelist if ('GET_PARAMETER' in x or 'SET_PARAMETER' in x )]
            for singlemessage in singlemessagelist:
              entrylist=singlemessage.split('\r')
              for entry in entrylist:
                if 'CSeq' in entry:
                  cseq = entry
                  resp='RTSP/1.0 200 OK\r'+cseq+'\r\n\r\n';#cseq contains \n
                  sock.sendall(resp)
                  logger.debug("<-{}".format(resp))



def setup_logger():
    logger = getLogger("PiCast")
    logger.setLevel(DEBUG)

    handler = StreamHandler()
    handler.setLevel(DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = True

setup_logger()

commands = {}
commands['01'] = 'SOURCE_READY'
commands['02'] = 'STOP_PROJECTION'
commands['03'] = 'SECURITY_HANDSHAKE'
commands['04'] = 'SESSION_REQUEST'
commands['05'] = 'PIN_CHALLENGE'
commands['06'] = 'PIN_RESPONSE'

types = {}
types['00'] = 'FRIENDLY_NAME'
types['02'] = 'RTSP_PORT'
types['03'] = 'SOURCE_ID'
types['04'] = 'SECURITY_TOKEN'
types['05'] = 'SECURITY_OPTIONS'
types['06'] = 'PIN_CHALLENGE'
types['07'] = 'PIN_RESPONSE_REASON'

uuidstr = str(uuid.uuid4()).upper()
hostname = socket.gethostname() 
print 'The hostname of this machine is: '+hostname

print uuidstr

dnsstr = 'avahi-publish-service '+hostname+' _display._tcp 7250 container_id={'+uuidstr+'}'
print dnsstr
os.system(dnsstr+' &')

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(('',7250))
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

sock.listen(1)

while True:
    (conn, addr) = sock.accept()
    print('Connected by', addr)
    p = PiCast(addr[0])
    os.system("sudo service kodi stop")
    
    while True:
        data = conn.recv(1024)
        # print data
        print data.encode('hex')

        if data == '':
            break

        size = int(data[0:2].encode('hex'),16)
        version = data[2].encode('hex')
        command = data[3].encode('hex')

        print (size,version,command)
        
        messagetype = commands[command]
        print messagetype

        if messagetype == 'SOURCE_READY':
            p.run()

        i = 4
        while i<size:
            tlvtypehex = data[i].encode('hex')
            valuelen = int(data[i+1:i+3].encode('hex'),16)
            value = data[i+3:i+3+valuelen]
            i = i+3+valuelen
            print (tlvtypehex,valuelen)
            tlvtype = types[tlvtypehex]
            print tlvtype,
            if tlvtype == 'FRIENDLY_NAME':
                print value

    conn.close()
    os.system("sudo service kodi start")

sock.close()

