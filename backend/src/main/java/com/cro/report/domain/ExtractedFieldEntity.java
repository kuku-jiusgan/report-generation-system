package com.cro.report.domain;
import jakarta.persistence.*;
import java.util.UUID;
@Entity @Table(name="extracted_field")
public class ExtractedFieldEntity {
 @Id public String id; @ManyToOne(optional=false) @JoinColumn(name="report_id") public ReportEntity report;
 @Column(name="field_code",nullable=false) public String fieldCode; @Column(nullable=false) public String label;
 @Column(name="raw_value",columnDefinition="text") public String rawValue; @Column(name="normalized_value",columnDefinition="text") public String normalizedValue;
 public String unit; @Column(nullable=false) public String status; @Column(name="source_type",nullable=false) public String sourceType;
 @Column(name="source_label",nullable=false) public String sourceLabel; @Column(name="source_detail",nullable=false,columnDefinition="text") public String sourceDetail;
 @Column(name="page_number") public Integer pageNumber; @Column(name="bbox_json") public String bboxJson;
 @Column(name="rule_expression",nullable=false,columnDefinition="text") public String ruleExpression;
 @Column(name="target_control_tag",nullable=false) public String targetControlTag;
 protected ExtractedFieldEntity(){}
 public ExtractedFieldEntity(String code,String label,String raw,String normalized,String unit,String status,String sourceType,String sourceLabel,String sourceDetail,Integer page,String rule,String tag){
  id=UUID.randomUUID().toString();fieldCode=code;this.label=label;rawValue=raw;normalizedValue=normalized;this.unit=unit;this.status=status;this.sourceType=sourceType;this.sourceLabel=sourceLabel;this.sourceDetail=sourceDetail;pageNumber=page;ruleExpression=rule;targetControlTag=tag;
 }
}

