# Shimadzu 인장시험기 자동화 DB 명세서

본 문서는 시마즈(Shimadzu) 인장시험기 자동화 시스템의 데이터베이스 구조를 정리한 상세 명세서입니다.

## 1. 프로젝트 정보

* **고객사**: 시마즈 (Shimadzu)
* **프로젝트명**: 인장시험기 자동화
* **DBMS**: MySQL
* **DB Name**: `shimadzu_db`
* **작성자**: 이정원
* **최종 수정일**: 2025.12.18

## 2. 테이블 목록 요약

| 순번 | 테이블명 | 설명 | 비고 | 
| ----- | ----- | ----- | ----- |
| 1 | `test_tray_items` | 트레이별 시편 시험 정보 | 실시간 모니터링 |
| 2 | `summary_data_items` | 전체 공정/작업 요약 이력 | - |
| 3 | `detail_data_items` | 상세 작업/공정 이력 데이터 | - |
| 4 | `batch_test_items` | 배치 시험 진행 순서 및 상태 | - |
| 5 | `batch_plan_items` | UI 설정 배치 계획 | VUI 설정 |
| 6 | `qr_recipe_items` | QR 레시피별 규격/치수 정보 | BATCH_QR |
| 7 | `batch_method_items` | 배치별 시험 방법 상세 설정 | BATCH_METHOD |

## 3. 테이블별 상세 명세

### 3.1 test_tray_items (트레이별 시편 정보)

각 트레이(10개)에 담긴 시편(5개)의 개별 상태를 실시간으로 관리합니다. 총 50개의 시편 정보를 가집니다.

| No | 컬럼명 | 타입 | 기본값 | 정의/설명 | 비고 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | `id` | INT | AI | 자동 증분 ID | PK | 
| 2 | `tray_no` | INT | - | 트레이 번호 (1-10) | - | 
| 3 | `specimen_no` | INT | - | 시편 번호 (1-5) | - | 
| 4 | `status` | INT | - | 상태 (0: 없음, 1: 대기, 2: 진행중, 3: 완료) | - | 
| 5 | `test_spec` | VARCHAR(50) | - | 시험규격 | - | 
| 6 | `dimension` | DECIMAL(10,3) | - | 치수 (XXmm) | - | 

### 3.2 summary_data_items (요약 데이터)

공정별 전체 작업 이력을 기록합니다.

| No | 컬럼명 | 타입 | 기본값 | 정의/설명 | 비고 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | `id` | INT | AI | 자동 증분 ID | PK | 
| 2 | `date_time` | DATETIME | - | 발생 일시 |-  | 
| 3 | `process_type` | VARCHAR(20) | - | 공정 타입 (공정/빈피킹) | - | 
| 4 | `batch_id` | VARCHAR(30) | - | 배치 ID | BATCH+TEST | 
| 5 | `tray_no` | INT | - | 트레이 번호 (1-10) | - | 
| 6 | `specimen_no` | INT | - | 시편 번호 (1-5) | - | 
| 7 | `work_history` | VARCHAR(50) | - | 작업 이력 (시작, 완료) | - | 

### 3.3 detail_data_items (상세 데이터)

각 단계별 상세 공정 기록을 저장합니다.

| No | 컬럼명 | 타입 | 기본값 | 정의/설명 | 비고 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | `date_time` | DATETIME | - | 발생 일시 | - | 
| 2 | `process_type` | VARCHAR(20) | - | 공정 타입 (공정/빈피킹) | - | 
| 3 | `batch_id` | VARCHAR(30) | - | 배치 ID | - | 
| 4 | `tray_no` | INT | - | 트레이 번호 (1-10) | - | 
| 5 | `specimen_no` | INT | - | 시편 번호 (1-5) | - | 
| 6 | `equipment` | VARCHAR(20) | - | 설비 (Robot, Device, EXT, User) | - | 
| 7 | `work_status` | VARCHAR(50) | - | 작업 상태 | - | 

### 3.4 batch_test_items (배치 시험 항목)

배치 단위의 시험 순서 및 현재 진행 상태를 관리합니다.

| No | 컬럼명 | 타입 | 기본값 | 정의/설명 | 비고 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | `id` | INT | AI | 자동 증분 ID | PK | 
| 2 | `tray_no` | INT | - | 트레이 번호 (1-10) | - | 
| 3 | `seq_order` | INT | - | 시험 순서 (1-10) | 0:없음 | 
| 4 | `seq_status` | INT | - | 시험 상태 (0:없음, 1:진행예정, 2:진행중, 3:완료) | - | 
| 5 | `test_method` | VARCHAR(50) | - | 시험 방법 | - | 
| 6 | `batch_id` | VARCHAR(50) | - | 배치 ID | - |
| 7 | `lot` | VARCHAR(50) | - | Lot 번호 | - |
| 8 | `qr_no` | VARCHAR(50) | '' | QR 레시피 번호 | NOT NULL |

### 3.5 batch_plan_items (배치 계획)

사용자가 UI에서 설정한 배치 시험 계획입니다.

| No | 컬럼명 | 타입 | 기본값 | 정의/설명 | 비고 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | `id` | INT | AI | 자동 증분 ID | PK | 
| 2 | `tray_no` | INT | - | 트레이 번호 (1-10) | - | 
| 3 | `seq_order` | INT | - | 시험 순서 (1-10) | - | 
| 4 | `seq_status` | INT | - | 시험 상태 (0:없음, 1:진행예정, 2:진행중, 3:완료) | - | 
| 5 | `test_method` | VARCHAR(50) | - | 시험 방법 (0:없음, 1:QR, n:방법n) | - | 
| 6 | `batch_id` | VARCHAR(50) | - | 배치 ID | - |
| 7 | `lot` | VARCHAR(50) | - | Lot 번호 | - |
| 8 | `qr_no` | VARCHAR(50) | '' | QR 레시피 번호 | NOT NULL |

### 3.6 qr_recipe_items (QR 레시피)

QR 코드를 통해 인식되는 시편의 치수 및 레시피 정보입니다.

| No | 컬럼명 | 타입 | 기본값 | 정의/설명 | 비고 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | `id` | INT | AI | 자동 증분 ID | PK | 
| 2 | `qr_no` | VARCHAR(50) | - | QR 레시피 번호 | - | 
| 3 | `batch_name` | VARCHAR(50) | - | 시험방법 파일명 | - | 
| 4 | `size1` | DECIMAL(6,2) | - | 사이즈1 | - | 
| 5 | `size2` | DECIMAL(6,2) | - | 사이즈2 | - | 
| 6 | `ql` | DECIMAL(6,2) | - | 길이 | - | 
| 7 | `chuckl` | DECIMAL(6,2) | - | 척(Chuck) 길이 | - | 
| 8 | `thickness` | DECIMAL(6,2) | - | 두께 | - | 

### 3.7 batch_method_items (배치 방법 상세)

배치별로 수정 가능한 시험 방법 및 규격 데이터입니다.

| No | 컬럼명 | 타입 | 기본값 | 정의/설명 | 비고 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | `id` | INT | AI | 자동 증분 ID | PK | 
| 2 | `qr_no` | VARCHAR(50) | - | QR 레시피 번호 | 수정 가능 | 
| 3 | `test_method` | VARCHAR(50) | - | 시험방법 파일명 | 수정 가능 | 
| 4 | `size1` | DECIMAL(6,2) | - | 사이즈1 | - | 
| 5 | `size2` | DECIMAL(6,2) | - | 사이즈2 | - | 
| 6 | `ql` | DECIMAL(6,2) | - | 길이 | - | 
| 7 | `chuckl` | DECIMAL(6,2) | - | 척 길이 | - | 
| 8 | `thickness` | DECIMAL(6,2) | - | 두께 | - | 
| 9 | `created_at` | DATETIME | - | 등록 일자 | 수정 가능 | 

## 4. 제약 조건 및 데이터 무결성

* **Primary Keys**: 모든 테이블은 `id` (INT, Auto-Increment) 컬럼을 PK로 사용하여 유일성을 보장합니다.
* **Reference**:
  * `batch_id`는 여러 테이블(`test_tray_items`, `summary_data_items`, `batch_plan_items` 등)에서 공통적으로 사용되어 데이터를 연결합니다.
  * `tray_no`와 `specimen_no`의 조합으로 특정 시편의 위치를 식별합니다.

## 5. 변경 이력

* **2025.02.11**: 초기 PDF 기반 명세서 작성
* **2025.12.18**: 엑셀 I/O 리스트 및 세부 테이블 9종 반영 (보강 완료)