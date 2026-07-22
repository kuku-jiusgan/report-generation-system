package com.cro.report.api;
import jakarta.persistence.EntityNotFoundException; import org.springframework.http.*; import org.springframework.web.bind.MethodArgumentNotValidException; import org.springframework.web.bind.annotation.*; import java.time.Instant; import java.util.Map;
@RestControllerAdvice public class ApiExceptionHandler {
 @ExceptionHandler(EntityNotFoundException.class) ResponseEntity<?> missing(Exception e){return ResponseEntity.status(404).body(Map.of("timestamp",Instant.now(),"error",e.getMessage()));}
 @ExceptionHandler(MethodArgumentNotValidException.class) ResponseEntity<?> invalid(MethodArgumentNotValidException e){return ResponseEntity.badRequest().body(Map.of("timestamp",Instant.now(),"error","Validation failed","fields",e.getFieldErrors().stream().map(x->x.getField()+": "+x.getDefaultMessage()).toList()));}
}

