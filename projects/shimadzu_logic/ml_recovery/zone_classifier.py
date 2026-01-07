"""
Zone-based State Classification

64개 상태를 5~6개 Zone으로 그룹화하여
적은 데이터로도 높은 정확도 달성
"""

from enum import IntEnum
from typing import Tuple, Optional
import logging

Logger = logging.getLogger(__name__)


class WorkZone(IntEnum):
    """작업 구역 정의"""
    UNKNOWN = 0
    RACK = 1                # 랙 (시편 픽업/배치)
    THICKNESS_GAUGE = 2     # 두께 측정기
    ALIGNER = 3             # 정렬기
    TENSILE_TESTER = 4      # 인장 시험기
    SCRAP_DISPOSER = 5      # 스크랩 처리기
    HOME = 6                # 홈 위치


class ZoneClassifier:
    """CMD ID를 Zone으로 매핑하는 분류기"""

    # CMD ID 범위 기반 Zone 매핑 (Command.md 기반)
    ZONE_MAPPING = {
        # 랙 관련 (1000~2100)
        WorkZone.RACK: [
            (1000, 1500),   # RACK_FRONT_MOVE, 픽업 관련
            (2000, 2100),   # RACK_FRONT_RETURN
            (1300, 1400),   # QR 스캔
        ],

        # 두께 측정기 (3000~4999)
        WorkZone.THICKNESS_GAUGE: [
            (3000, 3003),   # THICK_GAUGE_FRONT_MOVE, PLACE
            (3011, 3013),   # THICK_GAUGE_PICK
            (4000, 4002),   # THICK_GAUGE_RETURN
        ],

        # 정렬기 (5000~6999)
        WorkZone.ALIGNER: [
            (5000, 5012),   # ALIGNER_FRONT_MOVE, PLACE, PICK, WAIT
            (6000, 6000),   # ALIGNER_RETURN
        ],

        # 인장 시험기 (7000~8000)
        WorkZone.TENSILE_TESTER: [
            (7000, 7002),   # TENSILE_FRONT_MOVE, PLACE
            (7011, 7012),   # TENSILE_PICK
            (8000, 8000),   # TENSILE_RETURN
        ],

        # 스크랩 처리기 (7020~7022)
        WorkZone.SCRAP_DISPOSER: [
            (7020, 7022),   # SCRAP_FRONT_MOVE, DROP, RETURN
        ],

        # 홈 및 기본 동작 (1~100, 90~91)
        WorkZone.HOME: [
            (1, 6),         # HOME_XXX_FRONT
            (21, 26),       # XXX_FRONT_HOME
            (90, 91),       # GRIPPER_OPEN/CLOSE
            (100, 100),     # RECOVERY_HOME
        ],
    }

    @classmethod
    def cmd_to_zone(cls, cmd_id: int) -> WorkZone:
        """
        CMD ID를 WorkZone으로 변환

        Args:
            cmd_id: 로봇 모션 CMD ID

        Returns:
            해당하는 WorkZone
        """
        for zone, ranges in cls.ZONE_MAPPING.items():
            for start, end in ranges:
                if start <= cmd_id <= end:
                    return zone

        Logger.warning(f"[Zone Classifier] Unknown CMD {cmd_id}, returning UNKNOWN")
        return WorkZone.UNKNOWN

    @classmethod
    def zone_to_recovery_action(cls, zone: WorkZone) -> str:
        """
        Zone에 따른 복구 액션 결정

        Args:
            zone: 예측된 WorkZone

        Returns:
            복구 액션 문자열
        """
        # Command.md의 "정지 시 시편 버리기" 기반
        if zone in [WorkZone.THICKNESS_GAUGE, WorkZone.ALIGNER,
                    WorkZone.TENSILE_TESTER, WorkZone.SCRAP_DISPOSER]:
            return "RECOVER_WITH_SCRAP_DISPOSAL"  # 시편 있을 가능성
        else:
            return "RECOVER_TO_HOME"  # 시편 없음

    @classmethod
    def get_zone_name(cls, zone: WorkZone) -> str:
        """Zone을 한글 이름으로 변환"""
        names = {
            WorkZone.UNKNOWN: "알 수 없음",
            WorkZone.RACK: "랙",
            WorkZone.THICKNESS_GAUGE: "두께 측정기",
            WorkZone.ALIGNER: "정렬기",
            WorkZone.TENSILE_TESTER: "인장 시험기",
            WorkZone.SCRAP_DISPOSER: "스크랩 처리기",
            WorkZone.HOME: "홈/기본 동작",
        }
        return names.get(zone, "알 수 없음")

    @classmethod
    def get_zone_info(cls, zone: WorkZone) -> dict:
        """Zone의 상세 정보 반환"""
        info = {
            WorkZone.RACK: {
                "name_kr": "랙",
                "name_en": "Specimen Rack",
                "description": "시편 픽업/배치 구역",
                "typical_actions": ["픽업", "배치", "QR 스캔", "후퇴"],
            },
            WorkZone.THICKNESS_GAUGE: {
                "name_kr": "두께 측정기",
                "name_en": "Thickness Gauge",
                "description": "시편 두께 측정 구역",
                "typical_actions": ["배치", "측정", "회수", "후퇴"],
            },
            WorkZone.ALIGNER: {
                "name_kr": "정렬기",
                "name_en": "Aligner",
                "description": "시편 정렬 구역",
                "typical_actions": ["배치", "정렬", "회수", "대기"],
            },
            WorkZone.TENSILE_TESTER: {
                "name_kr": "인장 시험기",
                "name_en": "Tensile Tester",
                "description": "인장 시험 구역",
                "typical_actions": ["장착", "시험", "수거", "후퇴"],
            },
            WorkZone.SCRAP_DISPOSER: {
                "name_kr": "스크랩 처리기",
                "name_en": "Scrap Disposer",
                "description": "시편 폐기 구역",
                "typical_actions": ["이동", "버리기", "후퇴"],
            },
            WorkZone.HOME: {
                "name_kr": "홈/기본",
                "name_en": "Home",
                "description": "초기 위치 및 기본 동작",
                "typical_actions": ["홈 복귀", "그리퍼 개폐"],
            },
        }
        return info.get(zone, {})


if __name__ == "__main__":
    # 테스트
    test_cmds = [
        (24, "ALIGNER_FRONT_HOME"),
        (1050, "RACK 1F 시편 픽업"),
        (3001, "두께 측정기 배치"),
        (5001, "정렬기 배치"),
        (7011, "인장기 수거"),
        (7021, "스크랩 버리기"),
        (100, "홈 복귀"),
    ]

    print("=" * 60)
    print("Zone Classifier Test")
    print("=" * 60)

    for cmd_id, description in test_cmds:
        zone = ZoneClassifier.cmd_to_zone(cmd_id)
        zone_name = ZoneClassifier.get_zone_name(zone)
        recovery = ZoneClassifier.zone_to_recovery_action(zone)

        print(f"\nCMD {cmd_id:4d} ({description})")
        print(f"  → Zone: {zone_name} ({zone.name})")
        print(f"  → 복구: {recovery}")
