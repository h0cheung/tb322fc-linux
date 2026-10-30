// SPDX-License-Identifier: BSD-3-Clause
import { definePlugin, callable, toaster } from '@decky/api';
import { DropdownItem, PanelSection, PanelSectionRow, ToggleField, SliderField } from '@decky/ui';
import { useEffect, useState } from 'react';
import { FaExpandArrowsAlt, FaFilm } from 'react-icons/fa';
import { Tabs } from '../../shared/Tabs';
import { GamePicker, InstalledGame, useSelectedGame, gameName } from '../../shared/GamePicker';
import { editLaunchOptions } from '../../shared/launchOptions';
import { UpscalingTab } from './upscaling';
import { framegenOptions } from './launch';

const gamesCall = callable<[], InstalledGame[]>('installed_games');
type FG = { enabled: boolean; multiplier: string; flow_scale: number; preserve_images: boolean; bypass_wsi: boolean };
const getFG = callable<[number], FG>('fg_get');
const setFG = callable<[number, Partial<FG>], FG>('fg_set');
function FrameGen({ appid }: { appid: number }) {
  const [g, setG] = useState<FG | null>(null);
  useEffect(() => { setG(null); getFG(appid).then(setG); }, [appid]);
  if (!g) return null;
  const update = async (patch: Partial<FG>) => {
    try {
      const next = await setFG(appid, patch);
      if ('enabled' in patch) {
        try {
          await editLaunchOptions(appid, o => framegenOptions(o, next.enabled));
        } catch (e) {
          await setFG(appid, g);
          throw e;
        }
      }
      setG(next);
    } catch (e) { toaster.toast({ title: 'Kettle 插帧', body: String(e) }); }
  };
  return <PanelSection title="Kettle 插帧">
    <PanelSectionRow><ToggleField label="启用此游戏的 Kettle 插帧" checked={g.enabled} onChange={enabled => update({enabled})} description="下一次启动生效。启动器会停用 LSFG，避免两套插帧叠加。" /></PanelSectionRow>
    <PanelSectionRow><DropdownItem label="倍率" selectedOption={g.multiplier} rgOptions={[{data:'2',label:'2×'},{data:'3',label:'3×'},{data:'auto',label:'自动（2–3×或不插帧）'}]} onChange={o => update({multiplier:o.data})} /></PanelSectionRow>
    <PanelSectionRow><div style={{fontSize:12}}>在 Steam 性能菜单设置刷新率和帧率上限。固定2×时，建议基础帧率与显示帧率为1:2，例如30→60或60→120。插帧本身不会提高游戏逻辑帧率。</div></PanelSectionRow>
    <PanelSectionRow><SliderField label="运动估计分辨率" value={Math.round(g.flow_scale*100)} min={25} max={100} step={5} showValue valueSuffix="%" onChange={v=>update({flow_scale:v/100})} /></PanelSectionRow>
    <PanelSectionRow><ToggleField label="保留交换链图像数" checked={g.preserve_images} onChange={preserve_images=>update({preserve_images})} description="兼容性选项，修改后重启游戏。" /></PanelSectionRow>
    <PanelSectionRow><ToggleField label="绕过 Gamescope WSI" checked={g.bypass_wsi} onChange={bypass_wsi=>update({bypass_wsi})} description="修改后重启游戏。" /></PanelSectionRow>
  </PanelSection>;
}
const TABS = [
  {id:'up', label:'超分', icon:<FaExpandArrowsAlt/>},
  {id:'fg', label:'插帧', icon:<FaFilm/>},
];
let lastTab = TABS[0].id;

function Content() {
  const [games,setGames] = useState<InstalledGame[] | null>(null);
  const [appid,setAppid] = useSelectedGame(games);
  const [tab,setTab] = useState(lastTab);
  useEffect(()=>{gamesCall().then(setGames,e=>toaster.toast({title:'超分与插帧',body:String(e)}));},[]);
  return <>
    <PanelSection>
      <GamePicker games={games??[]} appid={appid} onChange={setAppid} />
      <Tabs tabs={TABS} tab={tab} onChange={t=>{lastTab=t;setTab(t);}} />
    </PanelSection>
    {tab==='up' ? <UpscalingTab appid={appid} name={appid?gameName(games,appid):''}/> : appid ? <FrameGen key={appid} appid={appid}/> : <div>请先选择一个游戏。</div>}
  </>;
}
export default definePlugin(()=>({name:'超分与插帧',title:<div>超分与插帧</div>,content:<Content/>,icon:<FaExpandArrowsAlt/>}));
