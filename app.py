from pathlib import Path
import pandas as pd
import streamlit as st
import altair as alt
from analysis import load_data, summarize, join_order

st.set_page_config(page_title='앉아가자 | 서울 버스',page_icon='🚌',layout='wide')
st.markdown('''<style>.stApp{background:#f7f9fc}h1{color:#173c37}div[data-testid="stMetric"]{background:white;padding:18px;border-radius:16px;border:1px solid #e1e8ec}</style>''',unsafe_allow_html=True)
st.caption('서울 버스 승하차 데이터 탐색')
st.title('앉아가자')
st.write('사람이 몰리는 정류장을 살펴보고, 조금 앞에서 타는 선택을 찾아보자.')
st.info('과거 월간 승하차 합계를 분석한다. 빈 좌석·착석 확률·실시간 혼잡도를 제공하지 않는다.')

@st.cache_data
def cached_load(path,modified): return load_data(path)

path=Path(__file__).parent/'bus_latest.csv'
if not path.exists(): st.error('bus_latest.csv가 필요하다.'); st.stop()
try: df=cached_load(str(path),path.stat().st_mtime_ns)
except Exception as e: st.error(str(e)); st.stop()
with st.sidebar:
    st.header('어떤 버스를 탈까?')
    month=st.selectbox('분석 월',sorted(df.use_ym.unique(),reverse=True))
    routes=sorted(df.loc[df.use_ym==month,'route_no'].unique())
    route=st.selectbox('버스 노선번호',routes,index=routes.index('143') if '143' in routes else 0)
    period=st.radio('시간대',['오전 07:00–09:00','오후 18:00–20:00'])
    st.caption('07·08시 또는 18·19시의 합계. 월 전체 요일을 포함한다.')
    order_file=st.file_uploader('방향별 정류장 순서 CSV (선택)',type='csv')
    st.caption('순서 파일을 등록하면 방향 선택과 앞선 정류장 대안을 사용할 수 있다.')
hours=[7,8] if period.startswith('오전') else [18,19]
try: summary=summarize(df,month,route,hours)
except ValueError as e: st.error(str(e)); st.stop()
ordered=None
if order_file:
    try:
        order=pd.read_csv(order_file,dtype=str)
        ordered=join_order(order,summary,route,month)
        direction=st.selectbox('운행 방향',ordered.direction.unique())
        ordered=ordered[ordered.direction==direction].reset_index(drop=True)
        view=ordered.copy()
        st.caption('정류장 순서 출처: '+', '.join(ordered.source_url.unique()))
    except Exception as e:
        st.error('순서 파일 확인 필요: '+str(e)); st.stop()
else: view=summary.sort_values('순승차',ascending=False)
st.subheader(f'{route}번 · {month[:4]}년 {month[4:]}월 · {period}')
a,b,c=st.columns(3)
a.metric('선택 범위 승차 합계',f'{int(view["승차"].sum()):,}명')
b.metric('선택 범위 하차 합계',f'{int(view["하차"].sum()):,}명')
c.metric('승차 집중 정류장',f'{int(view["승차 집중"].sum())}곳')
st.caption('단위는 월간 누적 인원이다. 1대당 또는 하루 평균 인원이 아니다.')
st.subheader('정류장별 순승차 인원')
if ordered is None: st.warning('운행 순서 미확인: 그래프는 순승차 내림차순이다. 앞선 정류장 추천은 보류한다.')
chart=alt.Chart(view).mark_bar(cornerRadiusEnd=3).encode(
    x=alt.X('순승차:Q',title='월간 승차 − 하차 (명)'),
    y=alt.Y('정류장:N',sort=view['정류장'].tolist(),title=None),
    color=alt.condition('datum["승차 집중"]',alt.value('#eb7855'),alt.value('#268879')),
    tooltip=['정류장','승차','하차','순승차','승차 집중']).properties(height=max(300,len(view)*23))
st.altair_chart(chart,use_container_width=True)
st.caption('주황색: 해당 노선 전체 정류장 순승차의 80백분위 이상이면서 순승차가 양수인 곳. 탐색용 기준이며 실제 혼잡 판정이 아니다.')
st.subheader('탑승 정류장 살펴보기')
target=st.selectbox('탑승 예정 정류장',view['정류장'].tolist())
selected=view[view['정류장']==target].iloc[0]
if selected['승차 집중']: st.warning(f'{selected.sttn_nm}: 승차 집중 지점이다. 순승차 {int(selected["순승차"]):,}명.')
else: st.write('이 정류장은 현재 기준에서 승차 집중 지점에 해당하지 않는다.')
if ordered is not None:
    idx=ordered.index[ordered['정류장']==target][0]
    alternatives=ordered.iloc[max(0,idx-2):idx]
    if not selected['승차 집중']: st.caption('앞선 정류장 대안은 승차 집중 지점을 선택하면 표시한다.')
    elif alternatives.empty: st.write('기점이므로 앞선 정류장이 없다.')
    else:
        st.write('앞선 1~2개 정류장 후보')
        st.dataframe(alternatives[['stop_sequence','정류장','승차','하차','순승차']],hide_index=True,use_container_width=True)
        st.caption('같은 방향의 앞선 정류장이다. 보행 가능 여부·배차·실제 차내 상황을 반영하지 않으며 착석을 보장하지 않는다.')
with st.expander('계산 방법과 데이터 한계'):
    st.write('순승차 = 선택 시간대 승차 합계 − 하차 합계. 시간대별 집계는 같은 차량의 이동을 추적하지 못하므로 누적해 재차 인원으로 해석하지 않는다. 월 통계에는 평일·주말이 섞여 있다. 노선과 정류장 ID로 연결하며, 방향·운행 순서는 별도 확인 자료만 사용한다. 동일 정류장이 여러 방향에서 공유되면 원본 통계가 방향별로 분리되지 않을 수 있다.')
    st.markdown('[승하차 통계](https://data.seoul.go.kr/dataList/OA-12913/F/1/datasetView.do) · [경유정류소 정보](https://data.seoul.go.kr/dataList/OA-15261/L/1/datasetView.do)')
st.download_button('분석 결과 CSV 저장',view.to_csv(index=False).encode('utf-8-sig'),file_name=f'bus_{route}_{month}.csv',mime='text/csv')
st.dataframe(view[['정류장','승차','하차','순승차','승차 집중']],hide_index=True,use_container_width=True)
