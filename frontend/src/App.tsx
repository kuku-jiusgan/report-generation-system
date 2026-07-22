import { useMemo, useState } from 'react';
import type { FocusEvent } from 'react';
import {
  Badge, Button, Caption1, Divider, Field, Input, Select, Spinner, Tab, TabList, Text, Title2, Tooltip,
} from '@fluentui/react-components';
import {
  ArrowDownload24Regular, ArrowSync24Regular, CheckmarkCircle20Filled, ChevronRight16Regular,
  DataUsage24Regular, DocumentEdit24Regular, DocumentPdf24Regular, ErrorCircle20Filled,
  History24Regular, Home24Regular, People24Regular, Play24Filled, Save24Regular, Settings24Regular,
  ShieldTask24Regular, Warning20Filled,
} from '@fluentui/react-icons';
import { demoReport } from './mock';
import type { ExtractedField, FieldStatus } from './types';

type Page = 'workspace' | 'templates' | 'rules' | 'sources' | 'users' | 'audit';
const nav: Array<{key:Page;label:string;icon:JSX.Element;group?:string}> = [
 {key:'workspace',label:'报告工作台',icon:<Home24Regular/>},
 {key:'templates',label:'模板管理',icon:<DocumentEdit24Regular/>,group:'后台管理'},
 {key:'rules',label:'提取规则',icon:<ShieldTask24Regular/>},
 {key:'sources',label:'数据源',icon:<DataUsage24Regular/>},
 {key:'users',label:'用户权限',icon:<People24Regular/>},
 {key:'audit',label:'运行记录',icon:<History24Regular/>},
];

function StatusMark({status}:{status:FieldStatus}) {
 const props:Record<FieldStatus,{text:string,color:'success'|'danger'|'warning'|'informative',icon:JSX.Element}> = {
  VALID:{text:'已验证',color:'success',icon:<CheckmarkCircle20Filled/>},
  MISSING:{text:'缺失',color:'danger',icon:<ErrorCircle20Filled/>},
  CONFLICT:{text:'冲突',color:'danger',icon:<ErrorCircle20Filled/>},
  WARNING:{text:'需确认',color:'warning',icon:<Warning20Filled/>},
 };
 const p=props[status]; return <Badge appearance="tint" color={p.color} icon={p.icon}>{p.text}</Badge>;
}

type Draft = {
 title:string; projectName:string; sampleName:string; batchNo:string;
 purposeHeading:string; purpose:string; conditionsHeading:string; column:string;
 flowRate:string; detector:string; linearityHeading:string; linearityLead:string;
 linearityR:string; linearityConclusion:string; loq:string;
};

const initialDraft:Draft = {
 title:'基因毒性杂质分析方法验证报告', projectName:'盐酸氟西汀基因毒杂质验证',
 sampleName:'盐酸氟西汀供试品', batchNo:'FXT240601', purposeHeading:'1. 验证目的',
 purpose:'建立并验证盐酸氟西汀中目标基因毒性杂质的定量分析方法，确认方法的专属性、线性、准确度、精密度及定量限满足预定要求。',
 conditionsHeading:'2. 色谱条件', column:demoReport.fields[3].normalizedValue??'', flowRate:'0.40 mL/min',
 detector:'质谱检测器', linearityHeading:'3. 线性与范围', linearityLead:'在规定浓度范围内进行线性回归。相关系数 r = ',
 linearityR:'0.9996', linearityConclusion:'，符合接受标准。', loq:'等待数据确认',
};

function EditableText({as:Tag='span',value,label,className,onChange,onFocus}:{
 as?:'span'|'h1'|'h2'|'p'|'td'|'mark'; value:string; label:string; className?:string;
 onChange:(value:string)=>void; onFocus?:()=>void;
}) {
 const commit=(event:FocusEvent<HTMLElement>)=>onChange(event.currentTarget.textContent??'');
 return <Tag className={['editable-text',className].filter(Boolean).join(' ')} contentEditable suppressContentEditableWarning
  spellCheck tabIndex={0} role="textbox" aria-label={label} onInput={onFocus} onFocus={onFocus} onBlur={commit}>{value}</Tag>;
}

function Workspace() {
 const [selected,setSelected]=useState<ExtractedField>(demoReport.fields[4]);
 const [busy,setBusy]=useState(false);
 const [panel,setPanel]=useState<'evidence'|'fields'>('evidence');
 const [draft,setDraft]=useState<Draft>(()=>{
  try { return {...initialDraft,...JSON.parse(localStorage.getItem('report-draft')??'{}')}; }
  catch { return initialDraft; }
 });
 const [dirty,setDirty]=useState(false);
 const [savedAt,setSavedAt]=useState(demoReport.updatedAt);
 const lims=useMemo(()=>demoReport.fields.filter(f=>f.evidence.sourceType==='ORACLE'),[]);
 const pdf=useMemo(()=>demoReport.fields.filter(f=>f.evidence.sourceType==='PDF'),[]);
 const run=(ms=900)=>{setBusy(true);window.setTimeout(()=>setBusy(false),ms)};
 const edit=<K extends keyof Draft>(key:K)=>(value:string)=>{setDraft(current=>({...current,[key]:value}));setDirty(true)};
 const markDirty=()=>setDirty(true);
 const save=()=>{
  localStorage.setItem('report-draft',JSON.stringify(draft));
  setSavedAt(new Date().toLocaleString('zh-CN',{hour12:false}));
  setDirty(false);
 };
 return <div className="workspace-page">
  <header className="record-header">
   <div><div className="crumb">报告任务 <ChevronRight16Regular/> {demoReport.reportNo}</div><Title2>{demoReport.title}</Title2>
    <div className="meta"><span>项目 {demoReport.projectNo}</span><span>样品 {demoReport.sampleNo}</span><span>实验 {demoReport.experimentNo}</span></div></div>
   <div className="record-actions">
    <Badge appearance="outline" color="success">数据已提取</Badge>
    <Button icon={<ArrowSync24Regular/>} onClick={()=>run()}>重新提取</Button>
    <Button appearance="primary" icon={<Play24Filled/>} onClick={()=>run(1200)}>生成新版本</Button>
   </div>
  </header>
  <div className="version-strip"><span>模板 {demoReport.templateVersion}</span><span>规则 {demoReport.ruleVersion}</span><span>最近保存 {savedAt}</span>{dirty&&<span className="unsaved">有未保存修改</span>}<span className="issue">1 个必填字段缺失，导出前必须确认</span></div>
  <main className="tri-pane">
   <aside className="source-pane left-pane">
    <div className="pane-title"><div><Text weight="semibold">LIMS 数据</Text><Caption1>Oracle 只读快照</Caption1></div><Badge>{lims.length}</Badge></div>
    <div className="source-summary"><div><span>项目记录</span><b>{demoReport.projectNo}</b></div><div><span>查询时间</span><b>14:32:18</b></div></div>
    <div className="field-list">{lims.map(f=><FieldRow key={f.fieldCode} field={f} selected={selected.fieldCode===f.fieldCode} onClick={()=>setSelected(f)}/>)}</div>
    <div className="snapshot-note"><CheckmarkCircle20Filled/> 已冻结查询快照<br/><small>V_REPORT_PROJECT / V_REPORT_SAMPLE</small></div>
   </aside>
   <section className="editor-pane">
    <div className="editor-toolbar">
     <div><Button size="small" appearance={dirty?'primary':'subtle'} icon={<Save24Regular/>} onClick={save}>保存版本</Button><Button size="small" appearance="subtle" icon={<ArrowDownload24Regular/>}>DOCX</Button><Button size="small" appearance="subtle" icon={<DocumentPdf24Regular/>}>PDF</Button></div>
     <span>{dirty?'正在编辑 · 尚未保存':'版本 3 · 编辑模式'}</span>
    </div>
    <div className="document-stage">
     {busy && <div className="busy"><Spinner label="正在处理报告，请勿关闭页面"/></div>}
     <article className="paper">
      <div className="report-code">报告编号：{demoReport.reportNo}</div>
      <EditableText as="h1" value={draft.title} label="报告标题" onChange={edit('title')} onFocus={markDirty}/>
      <div className="doc-rule"/>
      <table><tbody><tr><th>项目名称</th><EditableText as="td" value={draft.projectName} label="项目名称" className={selected.fieldCode==='project_name'?'active-cell':''} onChange={edit('projectName')} onFocus={()=>{markDirty();setSelected(demoReport.fields[0])}}/></tr><tr><th>样品名称</th><EditableText as="td" value={draft.sampleName} label="样品名称" onChange={edit('sampleName')} onFocus={()=>{markDirty();setSelected(demoReport.fields[1])}}/></tr><tr><th>样品批号</th><EditableText as="td" value={draft.batchNo} label="样品批号" onChange={edit('batchNo')} onFocus={()=>{markDirty();setSelected(demoReport.fields[2])}}/></tr></tbody></table>
      <EditableText as="h2" value={draft.purposeHeading} label="验证目的标题" onChange={edit('purposeHeading')} onFocus={markDirty}/><EditableText as="p" value={draft.purpose} label="验证目的正文" onChange={edit('purpose')} onFocus={markDirty}/>
      <EditableText as="h2" value={draft.conditionsHeading} label="色谱条件标题" onChange={edit('conditionsHeading')} onFocus={markDirty}/><table><tbody><tr><th>色谱柱</th><EditableText as="td" value={draft.column} label="色谱柱" onChange={edit('column')} onFocus={()=>{markDirty();setSelected(demoReport.fields[3])}}/></tr><tr><th>流速</th><EditableText as="td" value={draft.flowRate} label="流速" className={selected.fieldCode==='flow_rate'?'active-cell':''} onChange={edit('flowRate')} onFocus={()=>{markDirty();setSelected(demoReport.fields[4])}}/></tr><tr><th>检测器</th><EditableText as="td" value={draft.detector} label="检测器" onChange={edit('detector')} onFocus={markDirty}/></tr></tbody></table>
      <EditableText as="h2" value={draft.linearityHeading} label="线性与范围标题" onChange={edit('linearityHeading')} onFocus={markDirty}/><p><EditableText value={draft.linearityLead} label="线性说明" onChange={edit('linearityLead')} onFocus={markDirty}/><EditableText as="mark" value={draft.linearityR} label="线性相关系数" onChange={edit('linearityR')} onFocus={()=>{markDirty();setSelected(demoReport.fields[5])}}/><EditableText value={draft.linearityConclusion} label="线性结论" onChange={edit('linearityConclusion')} onFocus={markDirty}/></p>
      <div className="missing-line"><b>定量限：</b><EditableText value={draft.loq} label="定量限" onChange={edit('loq')} onFocus={()=>{markDirty();setSelected(demoReport.fields[6])}}/><ErrorCircle20Filled/></div>
      <div className="chart"><div className="axis y"/><div className="axis x"/><svg viewBox="0 0 500 145" role="img" aria-label="示例色谱图"><polyline points="0,122 80,121 118,116 124,15 132,121 218,120 300,119 362,116 371,43 380,119 500,120" fill="none" stroke="#0f6cbd" strokeWidth="2"/></svg></div>
      <div className="page-no">1 / 12</div>
     </article>
    </div>
   </section>
   <aside className="source-pane right-pane">
    <TabList selectedValue={panel} onTabSelect={(_,d)=>setPanel(d.value as 'evidence'|'fields')}><Tab value="evidence">PDF 图谱</Tab><Tab value="fields">提取字段</Tab></TabList>
    {panel==='evidence'?<>
     <div className="pdf-card"><div className="pdf-thumb"><DocumentPdf24Regular/><span>PDF</span></div><div><Text weight="semibold">EXP-HPLC-260718-03.pdf</Text><Caption1>12 页 · SHA-256 已校验</Caption1></div></div>
     <div className="pdf-preview"><div className="pdf-mini-head">HPLC Analysis Report</div><div className="pdf-lines"/><div className="highlight-box" style={{top:selected.evidence.page===6?'55%':'37%'}}>{selected.rawValue??'未找到匹配值'}</div><div className="chrom-line"/></div>
     <div className="evidence-detail"><div className="detail-head"><Text weight="semibold">{selected.label}</Text><StatusMark status={selected.status}/></div><dl><dt>原始值</dt><dd>{selected.rawValue??'无'}</dd><dt>标准化值</dt><dd>{selected.normalizedValue??'未填充'} {selected.unit}</dd><dt>来源</dt><dd>{selected.evidence.detail}</dd><dt>规则</dt><dd><code>{selected.rule}</code></dd><dt>目标标签</dt><dd><code>{selected.targetControlTag}</code></dd></dl></div>
    </>:<div className="field-list pdf-fields">{pdf.map(f=><FieldRow key={f.fieldCode} field={f} selected={selected.fieldCode===f.fieldCode} onClick={()=>setSelected(f)}/>)}</div>}
   </aside>
  </main>
 </div>
}

function FieldRow({field,selected,onClick}:{field:ExtractedField;selected:boolean;onClick:()=>void}) { return <button className={'field-row '+(selected?'selected':'')} onClick={onClick}><div><b>{field.label}</b><span>{field.normalizedValue??'未提取'} {field.unit}</span></div><StatusMark status={field.status}/></button> }

const templateRows=[['GTI-V1.3','基因毒杂质方法验证报告','已发布','12 个内容控件','2026-07-18'],['GTI-V1.2','基因毒杂质方法验证报告','历史版本','12 个内容控件','2026-05-09']];
function AdminPage({page}:{page:Exclude<Page,'workspace'>}) {
 const cfg={templates:['模板管理','管理 DOCX 内容控件、版本和发布状态'],rules:['提取规则','配置 Oracle 与 PDF 的确定性字段映射'],sources:['数据源','管理 Oracle 只读连接与视图白名单'],users:['用户权限','本地账号与角色访问控制'],audit:['运行记录','查询任务、导出和配置变更日志']}[page];
 return <div className="admin"><header><div><Title2>{cfg[0]}</Title2><p>{cfg[1]}</p></div><Button appearance="primary">{page==='templates'?'上传模板':page==='rules'?'新建规则版本':'新增'}</Button></header>
  {page==='templates'?<div className="admin-grid"><section className="admin-main"><div className="filterbar"><Input placeholder="搜索模板名称或版本"/><Select><option>全部状态</option><option>已发布</option></Select></div><table className="data-table"><thead><tr><th>版本</th><th>名称</th><th>状态</th><th>结构检查</th><th>更新时间</th></tr></thead><tbody>{templateRows.map(r=><tr key={r[0]}>{r.map((c,i)=><td key={c}>{i===2?<Badge color={i===2&&c==='已发布'?'success':'informative'}>{c}</Badge>:c}</td>)}</tr>)}</tbody></table></section><aside className="admin-side"><h3>发布门禁</h3>{['DOCX 可正常打开','内容控件标签唯一','必填标签完整','测试数据填充成功','渲染检查通过'].map(x=><div className="check" key={x}><CheckmarkCircle20Filled/>{x}</div>)}<Divider/><Button appearance="primary" disabled>发布当前版本</Button><Caption1>请选择一个待发布版本</Caption1></aside></div>:<GenericAdmin page={page}/>} 
 </div>
}
function GenericAdmin({page}:{page:Exclude<Page,'workspace'|'templates'>}) {
 if(page==='rules') return <div className="rule-layout"><aside>{['project_name','sample_name','column','flow_rate','linearity_r','loq'].map((x,i)=><button className={i===4?'active-rule':''} key={x}>{x}<Badge>{i===5?'异常':'有效'}</Badge></button>)}</aside><section className="rule-form"><h3>字段规则：linearity_r</h3><div className="form-grid"><Field label="来源类型"><Select><option>PDF</option><option>ORACLE</option></Select></Field><Field label="目标内容控件"><Input value="LINEARITY_R" readOnly/></Field><Field label="定位方式"><Select><option>文本锚点 + 正则</option><option>页面坐标</option></Select></Field><Field label="页码范围"><Input value="5-7" readOnly/></Field></div><Field label="提取表达式"><Input value={'r\\s*=\\s*(0\\.\\d+)'} readOnly/></Field><div className="test-result"><Play24Filled/><div><b>测试结果 0.9996</b><span>第 6 页，验证通过，来源坐标已记录</span></div><Button>运行测试</Button></div></section></div>;
 const labels=page==='sources'?['Oracle LIMS 主库','PDF 解析服务','对象存储 MinIO']:page==='users'?['系统管理员 admin','报告操作员 analyst01','只读查看者 viewer01']:['报告 GTI-VAL-2026-0047 已生成','模板 GTI-V1.3 已发布','PDF EXP-HPLC-260718-03 已解析'];
 return <div className="list-cards">{labels.map((x,i)=><div className="list-card" key={x}><div className="service-icon">{page==='audit'?<History24Regular/>:<DataUsage24Regular/>}</div><div><b>{x}</b><span>{page==='audit'?'2026-07-22 14:'+(36-i*2):i===0?'连接正常':'配置有效'}</span></div><Badge color={i===0?'success':'informative'}>{page==='audit'?'成功':'正常'}</Badge></div>)}</div>;
}

export function App() {
 const [page,setPage]=useState<Page>('workspace');
 return <div className="app-shell"><aside className="app-nav"><div className="brand"><div className="brand-mark">CR</div><div><b>报告智控</b><span>CRO Validation</span></div></div><nav>{nav.map((n,i)=><div key={n.key}>{n.group&&<div className="nav-group">{n.group}</div>}<Tooltip content={n.label} relationship="label"><button className={page===n.key?'active':''} onClick={()=>setPage(n.key)}>{n.icon}<span>{n.label}</span></button></Tooltip>{i===0&&<Divider/>}</div>)}</nav><div className="nav-user"><div>林</div><span><b>林岚</b><small>报告操作员</small></span><Settings24Regular/></div></aside><div className="app-content">{page==='workspace'?<Workspace/>:<AdminPage page={page}/>}</div></div>;
}
