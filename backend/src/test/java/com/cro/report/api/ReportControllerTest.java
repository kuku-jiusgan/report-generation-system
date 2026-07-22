package com.cro.report.api;
import org.junit.jupiter.api.Test; import org.springframework.beans.factory.annotation.Autowired; import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc; import org.springframework.boot.test.context.SpringBootTest; import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic; import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf; import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post; import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
@SpringBootTest @AutoConfigureMockMvc class ReportControllerTest {
 @Autowired MockMvc mvc;
 @Test void createsReport() throws Exception {mvc.perform(post("/api/reports").with(httpBasic("analyst","analyst-change-me")).with(csrf()).contentType("application/json").content("{\"projectNo\":\"P1\",\"sampleNo\":\"S1\",\"experimentNo\":\"E1\"}")).andExpect(status().isCreated()).andExpect(jsonPath("$.status").value("WAITING_UPLOAD"));}
}
