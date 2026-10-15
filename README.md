# bms2osu

BMS / BME / BML 채보를 **osu!mania** 채보(`.osu` / `.osz`)로 **일괄 변환**하는 도구입니다.
Python 표준 라이브러리만 사용하므로 별도 설치가 필요 없습니다. (Python 3.9+)

*English: a dependency-free batch converter from BMS/BME/BML charts to osu!mania beatmaps. Run `bms2osu --help`.*

## 사용법

```bash
# 폴더 전체(하위 폴더 포함)를 한 번에 변환 -> ./output/*.osz
python -m bms2osu "D:/BMS/Songs"

# 스크래치 제거 (7키), 출력 폴더 지정
python -m bms2osu "D:/BMS/Songs" --remove-scratch -o out

# 파일/폴더를 여러 개 지정
python -m bms2osu a.bme "D:/BMS/PackA" "D:/BMS/PackB"
```

릴리즈에서 받은 실행 파일(`bms2osu-windows.exe` 등)은 **폴더나 파일을 exe 위에 드래그 앤 드롭**해도 동작합니다.
생성된 `.osz` 파일을 더블클릭하거나 osu! 창에 끌어다 놓으면 가져와집니다.

### 옵션

| 옵션 | 설명 |
|---|---|
| `--remove-scratch` | 스크래치 노트를 제거합니다. 제거: **7키**(더블 14키) / 유지: **8키**(더블 16키) |
| `-o, --output DIR` | 출력 폴더 (기본 `./output`) |
| `--format osz\|osu` | `osz`(기본): 오디오 포함 패키지 / `osu`: 폴더에 `.osu` 파일로 저장 |
| `--audio NAME` | 오디오 파일명(각 폴더 기준) 또는 절대 경로. 생략 시 폴더에서 자동 선택 |
| `--creator NAME` | 채보 제작자 이름 |
| `--od N`, `--hp N` | OD / HP 값 (기본 8) |
| `--encoding ENC` | BMS 텍스트 인코딩 강제 지정 (기본: utf-8 → cp932 → cp949 순으로 자동) |
| `-j, --jobs N` | 병렬 처리 수 |
| `--no-recursive` | 폴더 하위 검색 안 함 |

## 변환 규칙

- BMS 파일이 들어 있는 **폴더 1개 = 비트맵셋(.osz) 1개**, 파일 1개 = 난이도 1개.
- 레인 배치(IIDX 방식): 스크래치 유지 시 `[스크래치][1~7]` (8키), 더블이면 `[스크][1~7][1~7][스크]` (16키).
- 지원: 마디 길이 변경(채널 02), BPM 변경(03 / 08), STOP(09), 롱노트(채널 5x/6x 및 `#LNOBJ`), `#RANDOM`(항상 1번 분기로 고정), 더블 플레이.
- BPM 변화는 osu! 타이밍 포인트로 기록됩니다. STOP은 노트 시간에 반영되지만 타이밍 그리드에는 표시되지 않습니다.

## 알려진 한계

- **키음 렌더링 미지원**: BMS는 노트마다 키음을 쓰지만 osu!는 곡 전체 오디오 1개를 재생합니다.
  키음을 하나로 믹싱한 오디오 파일(예: BMX2WAV 등으로 렌더링)을 같은 폴더에 두거나 `--audio`로 지정하세요.
  자동 선택은 폴더의 가장 큰 오디오 파일을 고르므로 결과를 꼭 확인하세요.
- BASE 62(`#BASE 62`), PMS(9키), 지뢰/히든 노트(채널 3x/Dx/Ex)는 지원하지 않습니다.
- 배경 이미지는 jpg/png만 포함됩니다. (osu!가 bmp를 지원하지 않음)
- 원작자의 허락 없이 변환한 곡을 osu!에 업로드/배포하지 마세요. 개인 플레이 용도를 권장합니다.

## 개발

```bash
python -m unittest discover -s tests -v
```

## GitHub 릴리즈 방법

1. GitHub에서 새 저장소를 만들고 이 폴더를 push 합니다.
   ```bash
   git init && git add . && git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/hanjw0126/bms2osu.git
   git push -u origin main
   ```
2. 버전 태그를 만들어 push 하면 **자동으로** 릴리즈가 만들어집니다.
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
3. GitHub Actions(`.github/workflows/release.yml`)가 테스트 후 Windows / macOS / Linux 실행 파일을 빌드하고,
   저장소의 **Releases** 페이지에 파일을 업로드합니다. (릴리즈 노트 자동 생성)

> 새 버전을 낼 때는 `pyproject.toml`과 `bms2osu/__init__.py`의 버전을 올린 뒤 새 태그를 push 하세요.
> 태그 없이 `main`에 `pyproject.toml` 변경을 push 하거나 Actions 탭에서 **Release** 워크플로를 수동 실행해도,
> `pyproject.toml`의 버전으로 `v<버전>` 태그와 릴리즈가 자동 생성됩니다.
