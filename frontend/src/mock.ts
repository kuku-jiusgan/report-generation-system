import type { Report } from './types';
export const demoReport: Report = {
 id:'7dbef44d-6bf2-4d5c-9b64-138789fb655a', reportNo:'GTI-VAL-2026-0047', projectNo:'PRJ-240871', sampleNo:'SMP-250119-A', experimentNo:'EXP-HPLC-260718-03',
 title:'N-亚硝基杂质分析方法验证报告', status:'READY', templateVersion:'GTI-V1.3', ruleVersion:'HPLC-PDF-V1.8', updatedAt:'2026-07-22 14:36',
 fields:[
  {fieldCode:'project_name',label:'项目名称',rawValue:'盐酸氟西汀基因毒杂质验证',normalizedValue:'盐酸氟西汀基因毒杂质验证',status:'VALID',targetControlTag:'PROJECT_NAME',rule:'LIMS.V_PROJECT.PROJECT_NAME',evidence:{sourceType:'ORACLE',label:'LIMS 项目主数据',detail:'V_REPORT_PROJECT.PROJECT_NAME'}},
  {fieldCode:'sample_name',label:'样品名称',rawValue:'盐酸氟西汀供试品',normalizedValue:'盐酸氟西汀供试品',status:'VALID',targetControlTag:'SAMPLE_NAME',rule:'LIMS.V_SAMPLE.SAMPLE_NAME',evidence:{sourceType:'ORACLE',label:'LIMS 样品记录',detail:'V_REPORT_SAMPLE.SAMPLE_NAME'}},
  {fieldCode:'batch_no',label:'样品批号',rawValue:'FXT240601',normalizedValue:'FXT240601',status:'VALID',targetControlTag:'BATCH_NO',rule:'LIMS.V_SAMPLE.BATCH_NO',evidence:{sourceType:'ORACLE',label:'LIMS 样品记录',detail:'V_REPORT_SAMPLE.BATCH_NO'}},
  {fieldCode:'column',label:'色谱柱',rawValue:'Waters ACQUITY BEH C18, 2.1×100 mm, 1.7 μm',normalizedValue:'Waters ACQUITY BEH C18（2.1 mm × 100 mm，1.7 μm）',status:'VALID',targetControlTag:'COLUMN_NAME',rule:'Anchor "Column" + line value',evidence:{sourceType:'PDF',label:'仪器方法页',detail:'第 2 页，方法参数表',page:2,bbox:[92,214,523,246]}},
  {fieldCode:'flow_rate',label:'流速',rawValue:'0.40 mL/min',normalizedValue:'0.40',unit:'mL/min',status:'VALID',targetControlTag:'FLOW_RATE',rule:'Flow rate regex + decimal(2)',evidence:{sourceType:'PDF',label:'仪器方法页',detail:'第 2 页，坐标区域',page:2,bbox:[91,282,521,310]}},
  {fieldCode:'linearity_r',label:'线性相关系数 r',rawValue:'0.9996',normalizedValue:'0.9996',status:'VALID',targetControlTag:'LINEARITY_R',rule:'r\\s*=\\s*(0\\.\\d+); range ≥ 0.995',evidence:{sourceType:'PDF',label:'线性结果表',detail:'第 6 页，回归统计',page:6,bbox:[78,394,541,444]}},
  {fieldCode:'loq',label:'定量限',rawValue:null,normalizedValue:null,unit:'ng/mL',status:'MISSING',targetControlTag:'LOQ',rule:'Anchor "LOQ" + numeric value; required',evidence:{sourceType:'PDF',label:'定量限结果',detail:'第 8 页未找到匹配值',page:8}},
 ]
};

