package com.cro.report.domain;
import jakarta.persistence.*; import java.time.Instant; import java.util.UUID;
@Entity @Table(name="report_version") public class ReportVersionEntity {
 @Id public String id; @Column(name="report_id",nullable=false) public String reportId; @Column(name="version_no",nullable=false) public int versionNo;
 @Column(nullable=false) public String reason; @Column(name="object_key") public String objectKey; public String sha256;
 @Column(name="created_by",nullable=false) public String createdBy; @Column(name="created_at",nullable=false) public Instant createdAt;
 protected ReportVersionEntity(){} public ReportVersionEntity(String reportId,int n,String reason,String key,String actor){id=UUID.randomUUID().toString();this.reportId=reportId;versionNo=n;this.reason=reason;objectKey=key;createdBy=actor;createdAt=Instant.now();}
}

