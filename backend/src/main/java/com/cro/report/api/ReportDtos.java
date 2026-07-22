package com.cro.report.api;
import jakarta.validation.constraints.NotBlank; import java.time.Instant; import java.util.List;
public final class ReportDtos {
 private ReportDtos(){}
 public record CreateReport(@NotBlank String projectNo,@NotBlank String sampleNo,@NotBlank String experimentNo,String title,String templateVersion,String ruleVersion){}
 public record Evidence(String sourceType,String label,String detail,Integer page,String bbox){}
 public record Field(String fieldCode,String label,String rawValue,String normalizedValue,String unit,String status,String targetControlTag,Evidence evidence,String rule){}
 public record ReportView(String id,String reportNo,String projectNo,String sampleNo,String experimentNo,String title,String status,String templateVersion,String ruleVersion,int currentVersion,Instant updatedAt,List<Field> fields){}
 public record JobAccepted(String jobId,String status,String message){}
 public record EditorConfig(String documentServerUrl,Object config,boolean available){}
}

