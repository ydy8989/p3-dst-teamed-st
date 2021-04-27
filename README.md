# 공용문서/대문/Pinned contents (임시)
### 여기에 지속적으로 공유되어야 할 내용들을 적습니다.
예를들어, rule book, working, roles, todo-list 등등

메모장처럼 쓰셔도 됩니다. 디자인 맘에 안들면 바꾸셔도 됩니다. 다른 사람이 쓴 것도 자유롭게 수정 가능

### 공유되어야 하지만, 숙지할 필요 없는것들은 이슈에 보관합니다.
예를 들어, 문제나 버그 해결 요청 -> 해결하고 끝.


# Top Prioirity(최우선 사항)
공지사항 or 현재 우선순위가 높은걸 최 상단에 노출  
PM.. PM이 필요하다...

### 하고있는거

재환 : 깃허브 탐방중, 협업에 대한 고민중

### 스케줄
8시에 아침 먹고 커피한잔 -> 9시에 출첵 겸 접속해서 30분정도 잡담
-> 9시30분에 QR코드 찍고 자유롭게 코딩, 오늘 뭐할지 생각 -> ...

전체 피어세션(10분) : 1시, 4시반, 9시 -> 전체를 대상으로 하는 내용에 대해서 간단히  
그 외 시간 : 간단한 질문 답변, 뭐하고 있는지 등등, 소소한것들 지속적으로 공유 가능

### 있으면 좋겠는거
깃허브의 코드를 바로 서버에서 실행하기  
6명 서버를 묶어서 사용하기

### 실제로 해야할거

"팀태스크 2개 & 개인작업" 으로 하면 좋지 않을까 생각됩니다.

<details><summary>EDA</summary>

- private 셋과 public 셋, train 셋에 분포차이 있는지 확인하기.

</details>

<details><summary>TRAIN</summary>

- 체계적인(단일화된) 하이퍼 파라미터 튜닝 환경(AutoKeras, tensorboard, ...)
- 효과적인 모델 아키텍쳐 탐색 / 논문 구현 (논문구현은 아마 2인1조로?)

</details>

<details><summary>DOCUMENTATION</summary>

- 학습내용과 연결해서 task 에 대한 분석  
- 작업한 내용들 정리(포트폴리오로 쓰는걸 대비)
- 피어세션에서 제안된 것들, 완료된 것들, 진행상황 등등, 필요한 것들 문서화 (서기역할)

</details>

<details><summary>P.S.</summary>

```
from jaehwan_codes import augmentation as aug
from semin_codes import use_server

data = aug.Augment(data, aug.SWAP)
server = use_server("124.51.62.1.")
server.train(trainer, data)
```

### 공용문서를 만들게 된 계기 : 효과적인 협업

대회기간이 4주이고, 모든 프로젝트는 항상 늦어진다는 점을 고려하면, 첫주에 "필요한 것들이 대부분 마무리"가 돼 있어야 나머지 기간동안
예외대처/사후처리, 추가개선 등을 진행할 수 있다고 예상합니다.

또한, 6명이서 협업을 하면 실질적으로 3명정도의 생산성이 나온다고 보면, 굉장히 긴밀하게 협업할 필요가 있다고 느꼈습니다.
그러면서도, 지난 스테이지까지 한명으로 학습정리하고, 컴피티션 참가하고 한것을 보면,
6명이라는 인원은 4명에 비해서 많은 것을 할 수 있는 인원이라고 생각됩니다.

단순히 data - model - 성능개선 - 대회 끝

으로 하기에는 아쉬우니, 첫주에 최대한 적극적으로, 많은 것들을 완성해서
이를 바탕으로 나머지 주에서 개선해가면 좋겠습니다.

### 작업중인 내용이나, todo-list 가 만들어지는 것에 부담을 느끼지 않았으면 합니다.
각자의 사정은 다릅니다. 밤에 코딩하는 사람도 있고, 주말에 밀린 강의를 듣는사람도 있을 것이며,
학교에서 중간고사가 있을수도 있죠. 각자가 코딩이 잘 될 때, 갑자기 흥미가 솓구칠 때에 더 많이 하는게 좋다고 생각합니다.
저같은경우에는 지금 글쓰기에 꽂혀서 이렇게 글을 많이 쓰고있습니다. 여담입니다 아무튼 각자의 목표도
조금씩 다를 수 있을 것 같습니다. 공부가 됐으면 하는 사람, 대회 등수가 중요한 사람, 면접준비, 포트폴리오 준비하는사람, 등등...
다만, 대회에서 성적을 높이기 위해 했던 수많은 시도와 노력들이 좋은 자산이 된다는건 다들 동의를 하실 듯 합니다.

개인적으로 저같은 경우, 부스트캠프에서 공부한것들, 작업한 것들을 포트폴리오로 만들어서 면접에서
평가받는거를 상상하면 좀 부담감이 느껴지면서 동기부여가 되더라구요.

적어도, 협업은 긴밀하게 되어야 한다고 생각합니다. 특히, 자기가 작업이 진행이 안된다,
그냥 오늘은 코딩하기가 싫다 이런것도 공유가 되어야 한다고 생각합니다. 이런 부분에 미안해하거나, 자책할 필요도 없고, 부담을 안가지셨으면 합니다.
학습플래너 같은걸 써본적이 있으실겁니다. 목표를 달성한 날을 기록해서 성취감을 느끼는 것도 중요하지만, 제대로 안된 날을 객관적으로(스스로) 확인하는 것도 중요합니다.
줌하다가 롤키셔도 되고, 유튜브 보셔도 됩니다. 스스로 컨디션 관리 잘 하시고, 자기자신에게 가장 잘 맞는 방법으로
팀프로젝트 수행하셨으면 합니다.

### 내가 편하기 위해 남을 돕는다
팀에게 도움이 될 만한건 뭐든 좋습니다. 마음껏 도와주셔도 됩니다.
다른 팀원에게 A를 알려주면, 그 팀원이 A를 이해하는데 드는 시간을 절약해서 B를 더 많이 작업할 수 있겠죠?
얼리스타터가 맨처음 어떻게 시작할지 알려주면, 레이트스타터가 시간을 절약할수도 있고,
강의를 안들은 사람, 마스터세션 까먹은사람(주로 저), 실험 잘못하고 있는 사람 등등, 조금이라도 도움이 되겠다 싶은 내용은
도움이 됩니다.(?)

### 그렇다고 불필요하게 잦은 회의는.. 안되겠죠?
특히, Pstage1의 랜덤매칭에서 할말도 없고.. 뭐라도 말하면서 시간을 떼운 적이 있죠...
물론, 특별히 중요한게 없으면 잡담하면서 할거하고 해도 괜찮습니다. 음.. 그러니까... 남에게 확실히 도움이 될 내용이 있으면
그런걸 주저하지 말고 말씀하시면 됩니다 ..!

</details>
