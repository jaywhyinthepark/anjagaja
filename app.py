from pathlib import Path
from html import escape
import pandas as pd
import streamlit as st
import altair as alt
from analysis import load_data, summarize, join_order, join_api, previous_candidates

st.set_page_config(page_title='앉아가자 | 서울 버스',page_icon='🚌',layout='wide')
st.markdown('''<style>
:root{--green:#03a85b;--ink:#202632;--line:#e6e9ed}
.stApp{background:#f3f5f7;color:var(--ink)}
.block-container{max-width:1400px;padding-top:2rem;padding-bottom:2rem}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--line)}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2{letter-spacing:-1px}
h1,h2,h3{color:var(--ink);letter-spacing:-.7px}
[data-testid="stMetric"]{background:#fff;padding:20px 24px;border-radius:12px;border:1px solid var(--line);box-shadow:0 2px 5px #182b3a04}
[data-testid="stMetricLabel"]{color:#6d7580}
[data-testid="stMetricValue"]{font-weight:750;font-size:1.8rem}
[data-testid="stSelectbox"] [data-baseweb="select"]>div{border-radius:9px;min-height:46px}
[data-testid="stDownloadButton"] button{background:var(--green);color:white;border:0;border-radius:8px;font-weight:700}
[data-testid="stExpander"]{background:#fff;border-radius:10px}
[data-testid="stDataFrame"]{border-radius:10px}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:18px}
.brand-icon{background:#03a85b;color:#fff;width:42px;height:42px;display:flex;align-items:center;justify-content:center;border-radius:13px;font-size:25px;font-weight:900}
.brand-name{font-size:26px;font-weight:850;letter-spacing:-1.2px}.brand-sub{font-size:12px;color:#78818d;margin-top:2px}
.hero{background:#fff;border:1px solid var(--line);border-radius:14px;padding:25px 28px;margin-bottom:22px}
.eyebrow{color:#03a85b;font-weight:750;font-size:12px;letter-spacing:1px}
.hero h1{font-size:30px;margin:5px 0 6px;padding:0;line-height:1.5}
.hero p{font-size:14px;color:#697480;margin:0;line-height:1.7}
.route-head{display:flex;align-items:center;gap:12px;margin:8px 0 18px;flex-wrap:wrap}
.bus-tag{background:#e7f6ef;color:#008448;border:1px solid #ccebdc;border-radius:7px;padding:6px 12px;font-size:19px;font-weight:800}
.route-meta{color:#6d7580;font-size:14px}
.stop-card{background:white;border:1px solid var(--line);border-radius:11px;padding:17px 18px;margin-bottom:12px;min-height:130px}
.stop-rank{color:#df693d;font-size:12px;font-weight:750}.stop-name{font-size:16px;font-weight:750;margin:8px 0;line-height:1.5}.stop-detail{color:#717b87;font-size:12px;line-height:1.8}
@media(max-width:640px){.block-container{padding:1rem}.hero{padding:19px}.hero h1{font-size:24px}.brand-name{font-size:23px}[data-testid="stMetric"]{padding:13px}}
</style>''',unsafe_allow_html=True)
st.markdown('''<div class="hero"><div class="eyebrow">SEOUL BUS EXPLORER</div><h1>조금 앞에서 타는 여유, 앉아가자</h1><p>출퇴근 시간, 사람들이 몰리는 정류장을 먼저 살펴보자.<br>과거 월간 통계를 분석하며 실제 빈 좌석이나 착석 확률을 제공하지 않는다.</p></div>''',unsafe_allow_html=True)

@st.cache_data
def cached_load(path,modified): return load_data(path)

path=Path(__file__).parent/'bus_latest.csv'
if not path.exists(): st.error('bus_latest.csv가 필요하다.'); st.stop()
try: df=cached_load(str(path),path.stat().st_mtime_ns)
except Exception as e: st.error(str(e)); st.stop()
api_path=Path(__file__).parent/'api_stops.csv'
@st.cache_data
def cached_api(path,modified): return pd.read_csv(path,dtype=str)
api=cached_api(str(api_path),api_path.stat().st_mtime_ns) if api_path.exists() else None
with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-icon">앉</div><div><div class="brand-name">앉아가자</div><div class="brand-sub">서울 버스 승하차 탐색</div></div></div>',unsafe_allow_html=True)
    st.subheader('버스 찾기')
    st.caption('노선번호를 입력해 검색할 수 있다.')
    month=st.selectbox('분석 월',sorted(df.use_ym.unique(),reverse=True))
    routes=sorted(df.loc[df.use_ym==month,'route_no'].unique())
    if api is not None:
        only_available=st.checkbox('운행 순서 확보 노선만 보기',value=True)
        if only_available: routes=sorted(set(routes)&set(api.queried_busRouteNm))
        st.caption(f'운행 순서와 통계가 연결된 노선 {len(set(df.route_no)&set(api.queried_busRouteNm))}개')
    route=st.selectbox('버스 노선번호',routes,index=routes.index('143') if '143' in routes else 0)
    period=st.radio('시간대',['오전 07:00–09:00','오후 18:00–20:00'])
    st.caption('07·08시 또는 18·19시의 합계. 월 전체 요일을 포함한다.')
    st.divider()
    with st.expander('운행 순서 자료 연결'):
        order_file=st.file_uploader('방향별 정류장 순서 CSV (선택)',type='csv')
        st.caption('자료를 등록하면 방향 선택과 앞선 정류장 대안을 사용할 수 있다.')
    st.caption('출처 · 서울 열린데이터광장')
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
elif api is not None:
    try: ordered=join_api(api,summary,route)
    except ValueError as e: st.warning(str(e)); ordered=None
    if ordered is not None:
        direction=st.selectbox('운행 방향',ordered.direction_label.unique())
        ordered=ordered[ordered.direction_label==direction].reset_index(drop=True)
        view=ordered.copy()
        st.caption('운행 순서: API '+str(ordered.collected_at.iloc[0])[:10]+' 수집 · 승하차 통계: '+month[:4]+'년 '+month[4:]+'월')
        st.caption('두 기준 시점의 노선 변경 여부는 확인이 필요하다. 연결되지 않는 정류장·반복 경유·회차 경계에서는 추천을 보류한다.')
        missing=int((~view['통계 연결']).sum())
        if missing: st.warning(f'이 방향의 {missing}개 정류장은 승하차 통계가 없어 그래프 값과 추천을 제공하지 않는다. 운행 순서에는 유지한다.')
    else: view=summary.sort_values('순승차',ascending=False)
else: view=summary.sort_values('순승차',ascending=False)
st.markdown(f'<div class="route-head"><span class="bus-tag">버스 {escape(route)}</span><span class="route-meta">{escape(month[:4])}년 {escape(month[4:])}월 &nbsp; / &nbsp; {escape(period)}</span></div>',unsafe_allow_html=True)
a,b,c=st.columns(3)
unique_view=view.drop_duplicates('std_bus_sttn_id')
a.metric('연결된 정류장 승차 합계',f'{int(unique_view["승차"].sum()):,}명')
b.metric('연결된 정류장 하차 합계',f'{int(unique_view["하차"].sum()):,}명')
c.metric('승차 집중 정류장',f'{int(unique_view["승차 집중"].sum())}곳')
st.caption('단위는 월간 누적 인원이다. 1대당 또는 하루 평균 인원이 아니다.')
st.subheader('승차가 집중되는 정류장')
top=unique_view[unique_view['승차 집중']].sort_values('순승차',ascending=False).head(3)
if top.empty:
    st.caption('현재 기준에 해당하는 승차 집중 정류장이 없다.')
else:
    for rank,(column,(_,stop)) in enumerate(zip(st.columns(len(top)),top.iterrows()),1):
        with column:
            st.markdown(f'<div class="stop-card"><div class="stop-rank">순승차 상위 {rank}</div><div class="stop-name">{escape(str(stop.sttn_nm))}</div><div class="stop-detail">월간 순승차 <b>+{int(stop["순승차"]):,}명</b><br>승차 {int(stop["승차"]):,} · 하차 {int(stop["하차"]):,}</div></div>',unsafe_allow_html=True)
st.subheader('정류장별 승하차 흐름')
if ordered is None: st.warning('운행 순서 미확인: 그래프는 순승차 내림차순이다. 앞선 정류장 추천은 보류한다.')
chart=alt.Chart(view).mark_bar(cornerRadiusEnd=3).encode(
    x=alt.X('순승차:Q',title='월간 승차 − 하차 (명)'),
    y=alt.Y('정류장:N',sort=view['정류장'].tolist(),title=None),
    color=alt.condition('datum["승차 집중"]',alt.value('#e77d50'),alt.value('#03a85b')),
    tooltip=['정류장','승차','하차','순승차','승차 집중']).properties(height=max(300,len(view)*23))
with st.container(height=520,border=True):
    st.altair_chart(chart.configure_view(strokeWidth=0).configure_axis(labelColor='#657180',titleColor='#657180',gridColor='#edf0f3'),use_container_width=True)
st.caption('주황색: 해당 노선 전체 정류장 순승차의 80백분위 이상이면서 순승차가 양수인 곳. 탐색용 기준이며 실제 혼잡 판정이 아니다.')
st.subheader('탑승 정류장 살펴보기')
target=st.selectbox('탑승 예정 정류장',view['정류장'].tolist())
selected=view[view['정류장']==target].iloc[0]
if pd.isna(selected['순승차']): st.warning('이 정류장과 연결되는 승하차 통계가 없다.')
elif selected['승차 집중']: st.warning(f'{selected.sttn_nm}: 승차 집중 지점이다. 순승차 {int(selected["순승차"]):,}명.')
else: st.write('이 정류장은 현재 기준에서 승차 집중 지점에 해당하지 않는다.')
if ordered is not None:
    idx=ordered.index[ordered['정류장']==target][0]
    alternatives=previous_candidates(ordered,idx)
    if not selected['승차 집중']: st.caption('앞선 정류장 대안은 승차 집중 지점을 선택하면 표시한다.')
    elif alternatives.empty: st.write('추천 가능한 앞선 정류장이 없다. 기점·회차·반복 경유·자료 누락 또는 앞선 정류장의 순승차가 더 낮지 않은 경우 추천을 보류한다.')
    else:
        st.write('앞선 1~2개 정류장 후보')
        st.dataframe(alternatives[['stop_sequence','정류장','승차','하차','순승차']],hide_index=True,use_container_width=True)
        st.caption('같은 방향의 앞선 1~2개 중 월간 순승차가 더 낮은 정류장이다. 보행 가능 여부·배차·실제 차내 상황을 반영하지 않으며 착석을 보장하지 않는다.')
with st.expander('계산 방법과 데이터 한계'):
    st.write('순승차 = 선택 시간대 승차 합계 − 하차 합계. 시간대별 집계는 같은 차량의 이동을 추적하지 못하므로 누적해 재차 인원으로 해석하지 않는다. 월 통계에는 평일·주말이 섞여 있다. 노선과 정류장 ID로 연결하며, 방향·운행 순서는 별도 확인 자료만 사용한다. 동일 정류장이 여러 방향에서 공유되면 원본 통계가 방향별로 분리되지 않을 수 있다.')
    st.markdown('[승하차 통계](https://data.seoul.go.kr/dataList/OA-12913/F/1/datasetView.do) · [경유정류소 정보](https://data.seoul.go.kr/dataList/OA-15261/L/1/datasetView.do)')
st.download_button('분석 결과 CSV 저장',view.to_csv(index=False).encode('utf-8-sig'),file_name=f'bus_{route}_{month}.csv',mime='text/csv')
st.dataframe(view[['정류장','승차','하차','순승차','승차 집중']],hide_index=True,use_container_width=True)
