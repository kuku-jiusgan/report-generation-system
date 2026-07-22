package com.cro.report.repo;
import com.cro.report.domain.ReportEntity; import org.springframework.data.jpa.repository.JpaRepository; import java.util.Optional;
public interface ReportRepository extends JpaRepository<ReportEntity,String>{Optional<ReportEntity> findByReportNo(String reportNo);}

