const fs=require('fs');const cp=require('child_process');const path=require('path');
const chunks=[
 ['孩子的故事，长辈哼的歌，还有妈妈在厨房里的一声笑。',7],
 ['这些声音，常常来不及保存，就消失在日常里。',6],
 ['家庭录音豆，替这一家人，轻轻记下它们。',7],
 ['它找到值得珍藏的片段，经家人确认，把一句原声，变成声音明信片。',8],
 ['再把几段原声串成故事，收进家庭留声机。',6],
 ['家人可以聆听、回应，也可以私密地分享。',5],
 ['多年后，他们再次听见彼此。每一声，都值得被记住。',6]
];
for(let i=0;i<chunks.length;i++){let [t,d]=chunks[i];const a=path.join(__dirname,'public',`voice-${i}.aiff`),o=a.replace('.aiff','.wav');cp.execFileSync('say',['-v','Tingting','-r','190','-o',a,t]);const len=Number(cp.execFileSync('ffprobe',['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',a]).toString());const speed=Math.max(.85,len/(d-.75));cp.execFileSync('ffmpeg',['-v','error','-y','-i',a,'-af',`atempo=${speed},afade=t=out:st=${d-.7}:d=0.3`,'-ar','48000',o]);console.log(i,len,speed);}
// Original, gentle ambient score synthesized for this film; no third-party music.
const sr=48000,duration=45,n=sr*duration,buf=Buffer.alloc(44+n*2);buf.write('RIFF');buf.writeUInt32LE(36+n*2,4);buf.write('WAVEfmt ',8);buf.writeUInt32LE(16,16);buf.writeUInt16LE(1,20);buf.writeUInt16LE(1,22);buf.writeUInt32LE(sr,24);buf.writeUInt32LE(sr*2,28);buf.writeUInt16LE(2,32);buf.writeUInt16LE(16,34);buf.write('data',36);buf.writeUInt32LE(n*2,40);
const chords=[[196,246.94,293.66],[164.81,196,246.94],[130.81,164.81,196],[146.83,185,220]];
for(let i=0;i<n;i++){const t=i/sr,ch=chords[Math.floor(t/6)%4];let v=0;for(let j=0;j<3;j++){v+=Math.sin(2*Math.PI*ch[j]*t)*.055*(.65+.35*Math.sin(Math.PI*(t%6)/6));}const local=t%1.5,note=ch[Math.floor(t/1.5)%3]*2;v+=Math.sin(2*Math.PI*note*local)*Math.exp(-local*4)*.10;v*=Math.min(1,t/2,(45-t)/3);buf.writeInt16LE(Math.round(Math.max(-1,Math.min(1,v))*22000),44+i*2);}fs.writeFileSync(path.join(__dirname,'public','music.wav'),buf);
