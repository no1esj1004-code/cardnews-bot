"""설정값 모음. 모든 값은 환경변수(.env 또는 GitHub Secrets/Variables)로 바꿀 수 있습니다."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
STATE_DIR = ROOT / "state"
ASSETS_DIR = ROOT / "assets"


def _load_dotenv() -> None:
    """로컬 실행용 .env 로더 (GitHub Actions에서는 Secrets가 환경변수로 들어옵니다)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = re.sub(r"\s+#.*$", "", value.strip())   # 값 뒤에 붙은 주석 제거
        os.environ.setdefault(key.strip(), value.strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str = "") -> str:
    # GitHub Actions는 설정 안 된 값을 빈 문자열로 넘기므로, 빈 값도 기본값으로 처리합니다.
    value = os.environ.get(name, "")
    return value if value != "" else default


def env_bool(name: str, default: bool) -> bool:
    return env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


# ── 채널 ────────────────────────────────────────────────────────────────
CHANNEL_NAME = env("CHANNEL_NAME", "지금뜨는")          # 카드 좌상단에 찍히는 채널 이름
CHANNEL_HANDLE = env("CHANNEL_HANDLE", "")              # 예: @jigeum.ddeuneun (마지막 카드에 표시)
# ── 마스코트 (채널 캐릭터가 설명해 주는 형식) ───────────────────────────
MASCOT = env_bool("MASCOT", True)                       # False면 캐릭터 없이 주제 이미지 + 어두운 디자인
MASCOT_SOURCE_FILE = ASSETS_DIR / "mascot_source.jpg"   # 모델이 되는 실제 고양이 사진 (있으면 이 사진을 바탕으로 캐릭터를 만듭니다)
MASCOT_FILE = ASSETS_DIR / "mascot.png"                 # 캐릭터 기준 그림 (python main.py mascot 으로 생성)
MASCOT_WAVE_FILE = ASSETS_DIR / "mascot_wave.png"       # 마지막 카드용 인사하는 그림

ACCENT_COLOR = env("ACCENT_COLOR", "#E8643C" if MASCOT else "#D7FF3E")   # 포인트 색
TOPIC_SCOPE = env("TOPIC_SCOPE", "연예·문화·밈")         # 다룰 주제 범위 (프롬프트에 그대로 들어갑니다)

# ── 운영 ────────────────────────────────────────────────────────────────
# 시험 모드. 정확히 false/0/no/off 로 적었을 때만 실제 게시합니다 (오타가 나면 안전한 쪽으로 동작).
DRY_RUN = env("DRY_RUN", "true").strip().lower() not in ("false", "0", "no", "off")
QUIET_HOURS = env("QUIET_HOURS", "")                    # 게시를 쉬는 시간대(KST). 예: "1-6" → 01~06시 쉼
MAX_POSTS_PER_DAY = env_int("MAX_POSTS_PER_DAY", 24)    # 24시간 동안 최대 게시 수
DEDUPE_HOURS = env_int("DEDUPE_HOURS", 72)              # 같은 주제를 다시 다루지 않는 기간
CANDIDATE_COUNT = env_int("CANDIDATE_COUNT", 16)        # 매시간 뉴스로 확인해 볼 실시간 검색어 수
HEADLINE_COUNT = env_int("HEADLINE_COUNT", 8)           # 후보에 넣을 연예 뉴스 묶음 수
MIN_SOURCES = env_int("MIN_SOURCES", 2)                 # 최소 몇 개 언론사 보도가 있어야 게시할지

# ── 트렌드 수집원 (쉼표로 나열, 빼고 싶은 것은 지우면 됩니다) ──────────
# google      구글 트렌드 실시간 검색어 RSS        무료, 키 불필요
# daum        다음 첫 화면 '실시간 트렌드'          무료, 키 불필요
# zum         줌 첫 화면 'AI 이슈트렌드'            무료, 키 불필요
# signal      시그널(signal.bz) 실시간 검색어       무료, 키 불필요
# google_news 구글 뉴스 '엔터테인먼트' 섹션 RSS     무료, 키 불필요
# youtube     유튜브 한국 인기 동영상 (참고 신호)   무료, YOUTUBE_API_KEY 필요
# dcinside    디시 실시간 베스트 제목 (참고 신호)   무료, 키 불필요
# x           X(트위터) 트렌드                      유료, X_BEARER_TOKEN 필요
TREND_SOURCES = [s.strip().lower() for s in
                 env("TREND_SOURCES", "google,daum,zum,signal,google_news,youtube,dcinside,x").split(",")
                 if s.strip()]
GOOGLE_TRENDS_GEO = env("GOOGLE_TRENDS_GEO", "KR")
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY")
X_BEARER_TOKEN = env("X_BEARER_TOKEN")
X_WOEID = env("X_WOEID", "23424868")                    # 대한민국 WOEID

# ── 네이버 뉴스 검색 (트렌드 키워드의 사실 확인용, 무료) ─────────────────
NAVER_CLIENT_ID = env("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = env("NAVER_CLIENT_SECRET")

# ── Threads 키워드 검색 (선택) ──────────────────────────────────────────
THREADS_ACCESS_TOKEN = env("THREADS_ACCESS_TOKEN")

# ── Claude (선별·요약·카피 작성) ────────────────────────────────────────
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = env("CLAUDE_MODEL", "claude-sonnet-5-5")

# ── AI 이미지 ───────────────────────────────────────────────────────────
OPENAI_API_KEY = env("OPENAI_API_KEY")
IMAGE_MODEL = env("IMAGE_MODEL", "gpt-image-2")
IMAGE_SIZE = env("IMAGE_SIZE", "1024x1536")             # 표지 (세로)
IMAGE_SIZE_BODY = env("IMAGE_SIZE_BODY", "1536x1024")   # 본문 카드 (가로)
IMAGE_QUALITY = env("IMAGE_QUALITY", "medium")          # low / medium / high — 낮출수록 싸고 빠릅니다
CARD_IMAGES = env_bool("CARD_IMAGES", True)             # False면 표지에만 이미지를 넣습니다

# ── 인스타그램 ──────────────────────────────────────────────────────────
IG_USER_ID = env("IG_USER_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN")
IG_API_VERSION = env("IG_API_VERSION", "v27.0")
# 카드 이미지가 공개적으로 열리는 주소의 앞부분.
# GitHub Actions에서는 워크플로가 자동으로 넣어줍니다 (media 브랜치의 raw 주소).
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL").rstrip("/")
