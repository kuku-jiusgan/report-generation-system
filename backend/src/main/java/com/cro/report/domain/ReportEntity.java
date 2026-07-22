package com.cro.report.domain;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;
@Entity @Table(name="report")
public class ReportEntity {
 @Id public String id; @Column(name="report_no",nullable=false,unique=true) public String reportNo;
 @Column(name="project_no",nullable=false) public String projectNo; @Column(name="sample_no",nullable=false) public String sampleNo;
 @Column(name="experiment_no",nullable=false) public String experimentNo; @Column(nullable=false) public String title;
 @Column(nullable=false) public String status; @Column(name="template_version",nullable=false) public String templateVersion;
 @Column(name="rule_version",nullable=false) public String ruleVersion; @Column(name="current_version",nullable=false) public int currentVersion;
 @Column(name="created_at",nullable=false) public Instant createdAt; @Column(name="updated_at",nullable=false) public Instant updatedAt;
 @OneToMany(mappedBy="report",cascade=CascadeType.ALL,orphanRemoval=true,fetch=FetchType.EAGER) public List<ExtractedFieldEntity> fields=new ArrayList<>();
 protected ReportEntity(){}
 public ReportEntity(String projectNo,String sampleNo,String experimentNo,String title,String templateVersion,String ruleVersion){
  this.id=UUID.randomUUID().toString();this.reportNo="GTI-VAL-"+Instant.now().toString().substring(0,10).replace("-","")+"-"+id.substring(0,4).toUpperCase();
  this.projectNo=projectNo;this.sampleNo=sampleNo;this.experimentNo=experimentNo;this.title=title;this.templateVersion=templateVersion;this.ruleVersion=ruleVersion;
  this.status="WAITING_UPLOAD";this.createdAt=Instant.now();this.updatedAt=this.createdAt;
 }
 public void addField(ExtractedFieldEntity f){f.report=this;fields.add(f);} public void touch(){updatedAt=Instant.now();}
}

