import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import argparse
import json
import platform
import time
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from channel_mix import ChannelMixer
from core import Processor, Controls, BLOCK, RATE, duplicate, select_stereo, StreamingResampler

def process_array(x, rate=RATE, controls=Controls()):
    p, r = Processor(), StreamingResampler(rate)
    out=[]; times=[]
    mixer=ChannelMixer()
    size=max(1, round(BLOCK*rate/RATE))
    for i in range(0,len(x),size):
        start=time.perf_counter()
        raw=x[i:i+size]
        if (controls.rear or controls.lfe or controls.center) and raw.ndim==2 and raw.shape[1]==6:
            pcm=np.clip(np.rint(raw*32768),-32768,32767).astype('<i2')
            raw=np.frombuffer(mixer.process(pcm.tobytes(),6,rate,controls.rear,controls.lfe,controls.limiter,center=controls.center),'<i2').reshape(-1,6).astype(np.float32)/32768
        block=r.process(select_stereo(raw))
        y=p.process(block, controls, now=i/rate)
        times.append((time.perf_counter()-start)*1000)
        out.append(duplicate(y))
    return np.concatenate(out) if out else np.empty((0,4)), times

def main():
    parser=argparse.ArgumentParser(description='오프라인 WAV 처리. 원본 파일은 덮어쓰지 않습니다.')
    parser.add_argument('input',type=Path); parser.add_argument('output',type=Path)
    parser.add_argument('--bypass',action='store_true')
    parser.add_argument('--limiter',choices=['hard','soft'],default='hard')
    parser.add_argument('--center',action='store_true',help='센터를 좌우에 추가')
    parser.add_argument('--rear',action='store_true',help='표준 5.1 WAV의 후방 L/R 추가')
    parser.add_argument('--lfe',action='store_true',help='표준 5.1 WAV의 LFE 추가')
    parser.add_argument('--strength',type=float,default=.55)
    parser.add_argument('--no-transient',action='store_true')
    parser.add_argument('--no-background',action='store_true')
    args=parser.parse_args()
    if args.output.exists(): parser.error('출력 파일이 이미 있습니다. 새 파일명을 지정하세요.')
    rate,x=wavfile.read(args.input)
    if x.ndim==1: x=x[:,None]
    if x.dtype==np.uint8: x=(x.astype(np.float32)-128)/128
    elif np.issubdtype(x.dtype,np.integer): x=x.astype(np.float32)/float(2**(np.iinfo(x.dtype).bits-1))
    else: x=x.astype(np.float32)
    y,t=process_array(x,rate,Controls(bypass=args.bypass,strength=args.strength,background=not args.no_background,transient=not args.no_transient,rear=args.rear,lfe=args.lfe,limiter=args.limiter,center=args.center))
    wavfile.write(args.output,RATE,y.astype(np.float32))
    print(json.dumps({'input_rate':rate,'output_rate':RATE,'frames':len(y),'dsp_ms_percentiles':np.percentile(t,[50,95,99,100]).tolist(),'hardware_haptics_test':False},indent=2))

if __name__=='__main__': main()
