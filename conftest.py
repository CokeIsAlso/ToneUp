"""pytest 루트 conftest.

이 파일이 저장소 루트에 있으면 pytest가 루트를 sys.path에 추가하므로
`pytest`를 어떤 방식으로 실행해도 `toneup` 패키지를 임포트할 수 있다.
(`python -m pytest`뿐 아니라 bare `pytest`, CI 환경 포함)
"""
