import React from 'react';
import {AbsoluteFill,Composition,Sequence,Audio,staticFile,useCurrentFrame,interpolate,registerRoot} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {FamilyScene,FadingScene,ProductScene,CardScene,RecordScene,ShareScene,FinaleScene} from './scenes/Scenes';
const scenes=[
 {start:0,len:7,component:FamilyScene,tag:'01 / 日常里的珍贵',title:['有些声音，','只发生一次。'],sub:'孩子的故事 · 长辈的歌 · 家人的笑声'},
 {start:7,len:6,component:FadingScene,tag:'02 / 那些来不及留下的',title:['日子向前，','声音渐远。'],sub:'珍贵的瞬间，常常藏在普通的一天'},
 {start:13,len:7,component:ProductScene,tag:'03 / 家庭录音豆',title:['轻轻记下，','一家人的声音。'],sub:'随手录音，把当下留住'},
 {start:20,len:8,component:CardScene,tag:'04 / 声音明信片',title:['一句原声，','一张有声的回忆。'],sub:'发现精彩片段 · 家人确认 · 配上照片'},
 {start:28,len:6,component:RecordScene,tag:'05 / 家庭留声机',title:['把零散的瞬间，','串成完整故事。'],sub:'温柔串讲，保留家人真实的声音'},
 {start:34,len:5,component:ShareScene,tag:'06 / 家庭声音互动',title:['被听见，','也被惦记。'],sub:'聆听 · 评论 · 私密分享'},
 {start:39,len:6,component:FinaleScene,tag:'家庭录音豆',title:['每一声，','都值得被记住。'],sub:'记录每一个声动时刻'},
];
const captions=[['孩子的故事，长辈哼的歌，','还有妈妈在厨房里的一声笑。'],['这些声音，常常来不及保存，','就消失在日常里。'],['家庭录音豆，','替这一家人，轻轻记下它们。'],['它找到值得珍藏的片段，经家人确认，','把一句原声，变成声音明信片。'],['再把几段原声串成故事，','收进家庭留声机。'],['家人可以聆听、回应，','也可以私密地分享。'],['多年后，他们再次听见彼此。','每一声，都值得被记住。']];
function Scene({index}:any){const f=useCurrentFrame();const s=scenes[index];const World=s.component;const opacity=interpolate(f,[0,12,s.len*24-12,s.len*24],[0,1,1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});return <AbsoluteFill style={{opacity}}>
 <ThreeCanvas width={1280} height={720} shadows camera={{position:[0,1,10.5],fov:38}} gl={{antialias:true,preserveDrawingBuffer:true}}><ambientLight intensity={1.6}/><directionalLight position={[-3,6,6]} intensity={3.0} castShadow shadow-mapSize={[1024,1024]} shadow-camera-left={-8} shadow-camera-right={8} shadow-camera-top={8} shadow-camera-bottom={-8}/><directionalLight position={[5,3,-2]} intensity={2} color='#f5d9b0'/><World f={f}/><mesh rotation={[-Math.PI/2,0,0]} position={[0,-2.25,0]} receiveShadow><planeGeometry args={[200,200]}/><shadowMaterial transparent opacity={.12}/></mesh></ThreeCanvas>
 <div style={{position:'absolute',left:74,top:133,width:490,color:'#173f38',transform:`translateY(${interpolate(f,[0,24],[18,0],{extrapolateRight:'clamp'})}px)`}}><div style={{fontSize:15,letterSpacing:4,color:'#aa7758',marginBottom:30}}>{s.tag}</div><div style={{fontFamily:'Songti SC, STSong, serif',fontSize:50,fontWeight:600,lineHeight:1.5,letterSpacing:1}}>{s.title.map(t=><div key={t}>{t}</div>)}</div><div style={{height:3,width:48,background:'#c38f66',margin:'28px 0'}}/><div style={{fontSize:19,lineHeight:1.8,color:'#64746c',maxWidth:420}}>{s.sub}</div></div>
 <div style={{position:'absolute',bottom:49,left:80,right:80,textAlign:'center',fontSize:22,color:'#344d43',lineHeight:1.5}}>{captions[index][f<s.len*12?0:1]}</div>
 <Sequence from={7} layout='none'><Audio src={staticFile(`voice-${index}.wav`)}/></Sequence>
 </AbsoluteFill>}
function Film(){const f=useCurrentFrame();return <AbsoluteFill style={{fontFamily:'PingFang SC, sans-serif',background:'radial-gradient(ellipse at 72% 35%, #fffdf5 0%, #f2ecdf 65%, #e5dac7 100%)'}}><div style={{position:'absolute',left:74,top:45,fontSize:15,letterSpacing:3,color:'#426054'}}>家庭录音豆 <span style={{color:'#a9afa0',marginLeft:15}}>FAMILY VOICE MEMORIES</span></div>{scenes.map((s,i)=><Sequence key={i} from={s.start*24} durationInFrames={s.len*24}><Scene index={i}/></Sequence>)}<div style={{position:'absolute',bottom:22,left:74,right:74,height:2,background:'#dadbcf'}}><div style={{width:`${f/1080*100}%`,height:2,background:'#ba8965'}}/></div><Audio src={staticFile('music.wav')} volume={.22}/></AbsoluteFill>}
registerRoot(()=> <Composition id='VoiceMemories' component={Film} width={1280} height={720} fps={24} durationInFrames={1080}/>);
