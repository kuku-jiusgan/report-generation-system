package com.cro.report.repo;
import com.cro.report.domain.ReportVersionEntity; import org.springframework.data.jpa.repository.JpaRepository; import java.util.List;
public interface ReportVersionRepository extends JpaRepository<ReportVersionEntity,String>{List<ReportVersionEntity> findByReportIdOrderByVersionNoDesc(String reportId);}

