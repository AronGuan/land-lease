-- 国有土地租赁智能管理 · MySQL 8.0 建表脚本 v1.0
-- 金额一律 DECIMAL(14,2)，计算在应用层用 Decimal，禁用 float
SET NAMES utf8mb4;

-- ============ 接入层 ============
CREATE TABLE IF NOT EXISTS import_batch (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_no     VARCHAR(64)  NOT NULL UNIQUE COMMENT '批次号，如 B-20261027-001',
  batch_type   VARCHAR(32)  NOT NULL COMMENT '存量合同/登记导出/缴费记录/减免登记/计租标准/现场补档',
  status       VARCHAR(32)  NOT NULL DEFAULT 'processing' COMMENT 'processing/reviewing/imported/rolled_back',
  file_count   INT NOT NULL DEFAULT 0,
  doc_count    INT NOT NULL DEFAULT 0,
  created_by   VARCHAR(64),
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  rolled_back_at DATETIME,
  INDEX idx_status (status), INDEX idx_created (created_at)
) ENGINE=InnoDB COMMENT='导入批次（撤回重导的骨架）';

CREATE TABLE IF NOT EXISTS file_object (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id   BIGINT NOT NULL,
  archive_no VARCHAR(32) NOT NULL COMMENT '档案号',
  page_no    INT NOT NULL DEFAULT 1,
  rel_path   VARCHAR(512) NOT NULL COMMENT '相对 storage 根目录，如 B-xx/LX-001/1.jpg',
  sha256     CHAR(64) NOT NULL COMMENT '完整性校验',
  mime       VARCHAR(64), size INT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_batch_path (batch_id, rel_path),
  INDEX idx_archive (archive_no), INDEX idx_sha (sha256)
) ENGINE=InnoDB COMMENT='原件元数据（图片存磁盘，绝不入 BLOB）';

-- ============ 合同层 ============
CREATE TABLE IF NOT EXISTS contract_doc (
  id            VARCHAR(32) PRIMARY KEY COMMENT '档案号 LX-001',
  batch_id      BIGINT NOT NULL,
  page_count    INT,
  doc_type      VARCHAR(16) COMMENT '新签/续期/变更',
  contract_no   VARCHAR(128), orig_contract_no VARCHAR(128),
  sign_date     DATE, lessor VARCHAR(128), lessee VARCHAR(128),
  lessee_type   VARCHAR(16) COMMENT '单位/个人',
  id_no         VARCHAR(64), phone VARCHAR(32), address VARCHAR(255),
  parcel_no     VARCHAR(64) COMMENT '宗地号（旧地号或单元号）',
  location      VARCHAR(255), area DECIMAL(14,2),
  land_usage    VARCHAR(32), land_level VARCHAR(16),
  start_date    DATE, end_date DATE, years INT,
  rent_mode     VARCHAR(32) COMMENT '固定/随标准调整',
  rate          DECIMAL(10,4) COMMENT '计租标准 元/㎡·年',
  rent_amount   DECIMAL(14,2) COMMENT '年租金小写',
  rent_amount_cn VARCHAR(128) COMMENT '年租金大写',
  has_map       TINYINT COMMENT '有无宗地图',
  altered_field VARCHAR(64), altered_before VARCHAR(255), altered_seal TINYINT,
  handwritten_note VARCHAR(512),
  process_type  VARCHAR(16) NOT NULL DEFAULT '自动通过' COMMENT '自动通过/人工复核',
  status        VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/reviewed/imported',
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_batch (batch_id), INDEX idx_status (status), INDEX idx_lessee (lessee)
) ENGINE=InnoDB COMMENT='合同要素（列名对齐 合同要素.csv）';

CREATE TABLE IF NOT EXISTS field_extraction (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  doc_id      VARCHAR(32) NOT NULL,
  field_name  VARCHAR(64) NOT NULL,
  ai_value    TEXT, final_value TEXT,
  confidence  DECIMAL(4,3) COMMENT '0~1',
  source      VARCHAR(16) NOT NULL COMMENT '直接识别/反推/人工录入',
  reason      JSON COMMENT '反推链路：evidence + rules + result',
  is_corrected TINYINT NOT NULL DEFAULT 0,
  corrected_by VARCHAR(64), corrected_at DATETIME,
  UNIQUE KEY uk_doc_field (doc_id, field_name),
  INDEX idx_source (source), INDEX idx_conf (confidence)
) ENGINE=InnoDB COMMENT='字段级抽取留痕（三级识别策略落库点）';

CREATE TABLE IF NOT EXISTS field_correction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  extraction_id BIGINT NOT NULL,
  before_value TEXT, after_value TEXT,
  operator VARCHAR(64), created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_ext (extraction_id)
) ENGINE=InnoDB COMMENT='人工修正记录（改前改后）';

-- ============ 宗地层 ============
CREATE TABLE IF NOT EXISTS parcel (
  parcel_key     VARCHAR(32) PRIMARY KEY COMMENT '最新一份新签或续期合同的档案号',
  unit_no        VARCHAR(64) COMMENT '不动产单元号（登记查不到留空）',
  reg_location   VARCHAR(255), reg_area DECIMAL(14,2), contract_area DECIMAL(14,2),
  land_usage     VARCHAR(32), land_level VARCHAR(16), rent_mode VARCHAR(32),
  contract_status VARCHAR(16) COMMENT '有效/到期未续/解除/收回',
  end_date       DATE, contract_lessee VARCHAR(128), reg_owner VARCHAR(128),
  dunning_target VARCHAR(128) COMMENT '催缴对象（第九条规则得出）',
  phone          VARCHAR(32),
  due_2026       DECIMAL(14,2), total_due DECIMAL(14,2),
  total_paid     DECIMAL(14,2), arrears DECIMAL(14,2),
  arrears_years  VARCHAR(512) COMMENT '欠缴年度，如 2002、2004、2026',
  process_type   VARCHAR(16) NOT NULL DEFAULT '自动通过',
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_unit (unit_no), INDEX idx_arrears (arrears)
) ENGINE=InnoDB COMMENT='一宗一档台账（列名对齐 宗地台账.csv）';

CREATE TABLE IF NOT EXISTS parcel_doc (
  parcel_key VARCHAR(32) NOT NULL, archive_no VARCHAR(32) NOT NULL,
  role       VARCHAR(16) COMMENT '新签/续期/变更',
  start_date DATE, end_date DATE,
  PRIMARY KEY (parcel_key, archive_no), INDEX idx_archive (archive_no)
) ENGINE=InnoDB COMMENT='宗地-文件关联（一宗多合同）';

CREATE TABLE IF NOT EXISTS registry_parcel (
  id       BIGINT AUTO_INCREMENT PRIMARY KEY,
  unit_no  VARCHAR(64), location VARCHAR(255), area DECIMAL(14,2),
  owner    VARCHAR(128), phone VARCHAR(32), raw_row JSON,
  INDEX idx_unit (unit_no), INDEX idx_owner (owner)
) ENGINE=InnoDB COMMENT='不动产登记导出';

CREATE TABLE IF NOT EXISTS registry_street_level (
  street_name VARCHAR(128) PRIMARY KEY, land_level VARCHAR(16) NOT NULL
) ENGINE=InnoDB COMMENT='街路→土地级别（合同未载级别时定级）';

-- ============ 规则层 ============
CREATE TABLE IF NOT EXISTS rent_standard (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  land_usage     VARCHAR(32) NOT NULL, land_level VARCHAR(16) NOT NULL,
  effective_from DATE NOT NULL, price DECIMAL(10,4) NOT NULL COMMENT '元/㎡·年',
  INDEX idx_lookup (land_usage, land_level, effective_from)
) ENGINE=InnoDB COMMENT='四套计租标准（1998/2009/2016/…）';

CREATE TABLE IF NOT EXISTS reduction_record (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  parcel_key VARCHAR(32), from_year INT, to_year INT,
  ratio DECIMAL(5,4) NOT NULL, doc_no VARCHAR(128),
  INDEX idx_parcel (parcel_key)
) ENGINE=InnoDB COMMENT='经批准的租金减免';

-- ============ 核算层 ============
CREATE TABLE IF NOT EXISTS rent_due (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  parcel_key VARCHAR(32) NOT NULL, year INT NOT NULL,
  months     INT COMMENT '当年计费月数（起租/终止当月均计入）',
  applied_rent DECIMAL(14,2) COMMENT '当年适用年租金',
  due_amount DECIMAL(14,2) NOT NULL, paid_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
  arrears    DECIMAL(14,2) NOT NULL DEFAULT 0,
  UNIQUE KEY uk_parcel_year (parcel_key, year), INDEX idx_arrears (arrears)
) ENGINE=InnoDB COMMENT='应缴明细（列名对齐 应缴明细.csv）';

CREATE TABLE IF NOT EXISTS rent_calc_trace (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  parcel_key VARCHAR(32) NOT NULL, year INT NOT NULL,
  rule_version VARCHAR(32) NOT NULL COMMENT '核算口径版本',
  input_snapshot JSON NOT NULL COMMENT '输入快照：面积/标准/减免/合同链',
  formula     VARCHAR(512), output DECIMAL(14,2),
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_parcel (parcel_key)
) ENGINE=InnoDB COMMENT='核算过程留痕（表2要求：过程可追溯）';

-- ============ 缴费层 ============
CREATE TABLE IF NOT EXISTS payment_record (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticket_no VARCHAR(64), parcel_key VARCHAR(32), pay_date DATE,
  amount DECIMAL(14,2), payer VARCHAR(128), note_year INT,
  is_duplicate TINYINT NOT NULL DEFAULT 0 COMMENT '同一票据号重复登记只计一次',
  raw_row JSON,
  INDEX idx_ticket (ticket_no), INDEX idx_parcel (parcel_key), INDEX idx_date (pay_date)
) ENGINE=InnoDB COMMENT='历年缴费流水';

CREATE TABLE IF NOT EXISTS payment_alloc (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  payment_id BIGINT NOT NULL, parcel_key VARCHAR(32) NOT NULL,
  year INT NOT NULL, amount DECIMAL(14,2) NOT NULL,
  alloc_rule VARCHAR(64) COMMENT '注明年度/冲抵最早欠缴年/多缴',
  INDEX idx_payment (payment_id), INDEX idx_parcel_year (parcel_key, year)
) ENGINE=InnoDB COMMENT='缴费归集（对齐 缴费归集.csv）';

-- ============ 问题层 ============
CREATE TABLE IF NOT EXISTS issue (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  target      VARCHAR(32) NOT NULL COMMENT '档案号（文件层）或宗地键（宗地层）',
  issue_type  VARCHAR(32) NOT NULL COMMENT '严格 13 类',
  description VARCHAR(1024),
  temp_algorithm VARCHAR(512) COMMENT '存疑暂按算法（第十二条）',
  diff_amount DECIMAL(14,2) COMMENT '与应缴最多算法相差金额',
  status      VARCHAR(16) NOT NULL DEFAULT 'open' COMMENT 'open/confirmed/resolved',
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_target (target), INDEX idx_type (issue_type)
) ENGINE=InnoDB COMMENT='问题清单（列名对齐 问题清单.csv）';

-- ============ 催缴层 ============
CREATE TABLE IF NOT EXISTS collection_notice (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  parcel_key VARCHAR(32) NOT NULL, arrears DECIMAL(14,2),
  template_version VARCHAR(32), file_path VARCHAR(512),
  status VARCHAR(16) NOT NULL DEFAULT 'generated' COMMENT 'generated/sent/closed',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_parcel (parcel_key)
) ENGINE=InnoDB COMMENT='催缴通知书';

CREATE TABLE IF NOT EXISTS sms_task (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  notice_id BIGINT NOT NULL, phone VARCHAR(32),
  status VARCHAR(16) NOT NULL DEFAULT '模拟发送' COMMENT '演示环境：模拟发送/已送达',
  sent_at DATETIME, INDEX idx_notice (notice_id)
) ENGINE=InnoDB COMMENT='短信任务（比赛阶段仅记录，不真实下发）';

CREATE TABLE IF NOT EXISTS payment_track (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  notice_id BIGINT NOT NULL, amount DECIMAL(14,2),
  pay_date DATE, receipt_no VARCHAR(64),
  INDEX idx_notice (notice_id)
) ENGINE=InnoDB COMMENT='缴纳结果跟踪 → 欠缴台账';

-- ============ 税务层 ============
CREATE TABLE IF NOT EXISTS tax_push (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  period VARCHAR(16) NOT NULL COMMENT '如 2026-Q4', year INT NOT NULL,
  row_count INT, total_amount DECIMAL(14,2),
  operator VARCHAR(64), created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='税务推送单（每次推送留存）';

CREATE TABLE IF NOT EXISTS tax_push_item (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  push_id BIGINT NOT NULL, parcel_key VARCHAR(32), unit_no VARCHAR(64),
  lessee VARCHAR(128), id_no VARCHAR(64), year INT,
  due_amount DECIMAL(14,2), paid_amount DECIMAL(14,2), arrears DECIMAL(14,2),
  INDEX idx_push (push_id)
) ENGINE=InnoDB COMMENT='推送单明细（字段按税务部门模板）';

-- ============ 支撑层 ============
CREATE TABLE IF NOT EXISTS sys_user (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL,
  real_name VARCHAR(64), role VARCHAR(32) NOT NULL COMMENT 'admin/officer/reviewer',
  status VARCHAR(16) NOT NULL DEFAULT 'enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='用户与权限';

CREATE TABLE IF NOT EXISTS audit_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  actor VARCHAR(64) NOT NULL, action VARCHAR(64) NOT NULL COMMENT '字段修正/确认入库/批次导入/批次撤回/租金重算/模型切换',
  target_type VARCHAR(64), target_id VARCHAR(64),
  before_value TEXT, after_value TEXT, context JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_actor (actor), INDEX idx_action (action), INDEX idx_created (created_at)
) ENGINE=InnoDB COMMENT='审计日志（append-only）';

CREATE TABLE IF NOT EXISTS model_config (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(64) NOT NULL, channel VARCHAR(16) NOT NULL COMMENT 'cloud/local',
  endpoint VARCHAR(255), model_id VARCHAR(128),
  is_active TINYINT NOT NULL DEFAULT 0, params JSON
) ENGINE=InnoDB COMMENT='模型注册表（可配置可切换）';

CREATE TABLE IF NOT EXISTS model_call_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  model_name VARCHAR(128), target VARCHAR(128),
  duration_ms INT, tokens INT, avg_confidence DECIMAL(4,3),
  result VARCHAR(32), created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='模型调用日志';

CREATE TABLE IF NOT EXISTS config_item (
  config_key VARCHAR(64) PRIMARY KEY, config_value TEXT, remark VARCHAR(255)
) ENGINE=InnoDB COMMENT='配置中心：口径版本/置信度阈值/提醒分级/模板';

CREATE TABLE IF NOT EXISTS backup_record (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  backup_type VARCHAR(16), file_path VARCHAR(512),
  sha256_status VARCHAR(16), created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='备份记录（MySQL dump + storage 目录）';
