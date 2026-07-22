create table report (
 id varchar(36) primary key, report_no varchar(64) not null unique, project_no varchar(64) not null,
 sample_no varchar(64) not null, experiment_no varchar(64) not null, title varchar(255) not null,
 status varchar(32) not null, template_version varchar(64) not null, rule_version varchar(64) not null,
 current_version integer not null default 0, created_at timestamp not null, updated_at timestamp not null
);
create table extracted_field (
 id varchar(36) primary key, report_id varchar(36) not null references report(id), field_code varchar(128) not null,
 label varchar(255) not null, raw_value text, normalized_value text, unit varchar(32), status varchar(32) not null,
 source_type varchar(16) not null, source_label varchar(255) not null, source_detail text not null,
 page_number integer, bbox_json varchar(255), rule_expression text not null, target_control_tag varchar(128) not null,
 unique(report_id, field_code)
);
create table report_version (
 id varchar(36) primary key, report_id varchar(36) not null references report(id), version_no integer not null,
 reason varchar(32) not null, object_key varchar(512), sha256 varchar(64), created_by varchar(128) not null,
 created_at timestamp not null, unique(report_id, version_no)
);
create table audit_log (
 id varchar(36) primary key, actor varchar(128) not null, action varchar(64) not null, object_type varchar(64) not null,
 object_id varchar(128) not null, detail text, occurred_at timestamp not null
);
create index idx_field_report on extracted_field(report_id);
create index idx_audit_occurred on audit_log(occurred_at);

