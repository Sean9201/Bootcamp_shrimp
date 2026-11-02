# data (git 제외)

이 폴더의 내용은 이 README 를 빼고 git 에 올라가지 않습니다.

```
data/
  raw/<YYYY-MM-DD>/      수집한 원본 녹음 (손대지 않음)
  sessions/<session_id>/ 정리된 세션: audio.wav + meta.json (+ clicks.csv)
  splits/                학습·검증·테스트 분할 목록
  synthetic/             합성 데이터
```

데이터셋 버전(날짜, 세션 수, 변경 내용)은 상위 README 의 "데이터셋 버전" 표에 기록합니다.
