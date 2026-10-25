# subsidy_total_forme

기업용·개인용 보조금 API 수집 코드와 데이터를 한 저장소에서 관리합니다. 기존 저장소는 수정하지 않았습니다. 이 저장소는 API/데이터 통합용이며 기존 두 웹사이트 화면을 합친 앱은 아닙니다.

## 옮긴 구성

- business/scripts, business/data: [bizzsubsidy](https://github.com/jungs311311/bizzsubsidy)의 기업마당 수집·공고문 분석·조건표 데이터
- personal/scripts, personal/data: [personalsubsidy](https://github.com/jungs311311/personalsubsidy)의 보조금24·복지로 중앙/지자체·온통청년 수집·기준표 데이터
- scripts/update_all.py: 두 수집기를 실행하는 통합 진입점
- .github/workflows/update-all.yml: 매일 한국시간 오전 7시 23분 자동 실행, 수동 실행도 가능. GitHub 사정으로 지연될 수 있습니다.
- data/sync-status.json: 실행 시각과 소스별 API/원본 동기화 결과. 실제 자료의 기준 시각은 각 데이터 파일 안의 updated 등을 확인하세요.

## 세 가지 실행 모드

Actions → 기업·개인 보조금 매일 갱신 → Run workflow → mode 선택

- auto (기본): 등록된 인증키가 있으면 직접 API 수집. 키가 없거나 호출 실패 시 원본 저장소의 최신 공개 JSON으로 동기화합니다.
- api: 모든 소스를 직접 API 호출합니다. 필요한 키가 없거나 호출에 실패하면 실패로 표시하고 기존 파일을 보존합니다.
- mirror: 인증키 없이 원본 저장소의 공개 JSON을 동기화합니다. 원본의 자동 갱신에 의존하며 원본 수집이 멈추면 이곳 자료도 최신이 아닐 수 있습니다.

## 직접 API 호출용 인증키 등록

Settings → Secrets and variables → Actions → New repository secret

- BIZINFO_KEY: 기업마당 인증키 (기존 bizzsubsidy에서 사용)
- ODCLOUD_KEY 또는 GOV24_KEY: 공공데이터포털 일반 인증키 (기존 personalsubsidy에는 ODCLOUD_KEY로 등록됨)
- YOUTH_KEY: 온통청년 인증키 (기존 personalsubsidy에서 사용)
- BOKJIRO_KEY: 복지로 전용 키가 별도일 때 선택 등록. 없으면 GOV24_KEY/ODCLOUD_KEY를 함께 사용합니다. 해당 API 활용 승인도 필요합니다.

GitHub Secrets의 기존 값은 다시 조회하거나 저장소 간 복사할 수 없습니다. 새 저장소에는 발급받은 값을 다시 입력해야 합니다. 인증키를 코드·README·데이터에 적지 마세요. 키 등록 전에도 auto/mirror 모드의 자동 동기화는 작동합니다.

두 원본의 공개 구글 시트 연결은 유지했습니다. 매일 실행할 때 최신 조건표를 읽고, 실패 시 원본 JSON으로 대체합니다. 시트 문구 수정은 기존 시트에서 하세요.

로컬 실행(Python 3.12):

```sh
pip install -r requirements.txt
python scripts/update_all.py --mode auto
```

API 기본 필터도 원본과 동일합니다. 기업은 소상공인·개인사업자 관련 공고, 개인은 전국·대구·경북 중심의 자료이며 전국 모든 지원금을 빠짐없이 담는 데이터는 아닙니다. 실제 신청 자격·기간은 각 기관 공고를 확인하세요.
