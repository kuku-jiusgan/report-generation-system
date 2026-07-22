export type FieldStatus = 'VALID' | 'MISSING' | 'CONFLICT' | 'WARNING';
export type SourceType = 'ORACLE' | 'PDF';
export interface Evidence { sourceType: SourceType; label: string; detail: string; page?: number; bbox?: [number,number,number,number]; }
export interface ExtractedField { fieldCode:string; label:string; rawValue:string|null; normalizedValue:string|null; unit?:string; status:FieldStatus; targetControlTag:string; evidence:Evidence; rule:string; }
export interface Report { id:string; reportNo:string; projectNo:string; sampleNo:string; experimentNo:string; title:string; status:string; templateVersion:string; ruleVersion:string; updatedAt:string; fields:ExtractedField[]; }

