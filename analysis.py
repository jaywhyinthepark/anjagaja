import pandas as pd

def load_data(path):
    df = pd.read_csv(path, dtype=str, encoding='utf-8-sig')
    required = ['use_ym','route_no','std_bus_sttn_id','sttn_nm']
    required += [f'hh{h:02d}_{kind}_tot_psgr_cnt' for h in [7,8,18,19] for kind in ['ride','gff']]
    missing = set(required)-set(df.columns)
    if missing: raise ValueError('필수 열 누락: '+', '.join(sorted(missing)))
    for col in required[4:]:
        df[col] = pd.to_numeric(df[col], errors='raise')
        if df[col].isna().any() or (df[col]<0).any(): raise ValueError('승하차 인원에 결측값 또는 음수가 있다: '+col)
    return df

def summarize(df, month, route, hours):
    part=df[(df.use_ym==month)&(df.route_no==route)].copy()
    part['승차']=part[[f'hh{h:02d}_ride_tot_psgr_cnt' for h in hours]].sum(axis=1)
    part['하차']=part[[f'hh{h:02d}_gff_tot_psgr_cnt' for h in hours]].sum(axis=1)
    # 정류장 이름이 같아도 ID가 다르면 합치지 않는다.
    result=part.groupby('std_bus_sttn_id',as_index=False).agg(
        sttn_nm=('sttn_nm',lambda names: ' / '.join(sorted(set(names.dropna())))),
        승차=('승차','sum'),하차=('하차','sum'))
    result['순승차']=result['승차']-result['하차']
    threshold=result['순승차'].quantile(.8)
    result['승차 집중']=(result['순승차']>0)&(result['순승차']>=threshold)
    result['정류장']=result.sttn_nm+' ['+result.std_bus_sttn_id+']'
    return result

def join_order(order, summary, route, month):
    needed={'route_no','use_ym','direction','stop_sequence','std_bus_sttn_id','source_url'}
    if not needed.issubset(order.columns): raise ValueError('순서 파일 필수 열: '+', '.join(sorted(needed)))
    o=order[(order.route_no==route)&(order.use_ym==month)].copy()
    if o.empty: raise ValueError('선택한 노선·월의 정류장 순서가 없다.')
    if o[list(needed)].isna().any().any() or o.source_url.str.strip().eq('').any(): raise ValueError('순서와 출처를 모두 입력해야 한다.')
    o['stop_sequence']=pd.to_numeric(o.stop_sequence,errors='raise')
    if (o.stop_sequence<1).any() or (o.stop_sequence%1!=0).any(): raise ValueError('운행 순서는 양의 정수여야 한다.')
    if o.duplicated(['direction','stop_sequence']).any(): raise ValueError('방향별 운행 순서가 중복된다.')
    for _,g in o.groupby('direction'):
        seq=sorted(g.stop_sequence.astype(int))
        if seq!=list(range(1,len(seq)+1)): raise ValueError('방향별 전체 정류장을 1부터 빠짐없이 입력해야 한다.')
        if g.std_bus_sttn_id.duplicated().any(): raise ValueError('반복 경유 정류장의 통계는 통과 차수별로 구분되지 않아 추천할 수 없다.')
    joined=o.merge(summary,on='std_bus_sttn_id',how='left',validate='many_to_one')
    if joined['순승차'].isna().any(): raise ValueError('통계와 일치하지 않는 정류장 ID가 있다.')
    return joined.sort_values(['direction','stop_sequence'])

def join_api(api, summary, route):
    o=api[api.queried_busRouteNm==route].copy()
    if o.empty: return None
    if o.queried_busRouteId.nunique()!=1:
        raise ValueError('같은 노선번호에 API 노선 ID가 여러 개여서 자동 추천을 보류한다.')
    o['stop_sequence']=pd.to_numeric(o.seq,errors='raise').astype(int)
    o=o.sort_values('stop_sequence').reset_index(drop=True)
    if o.stop_sequence.duplicated().any(): raise ValueError('API 정차 순서가 중복된다.')
    o['direction']=o.direction.fillna('방향 미확인')
    # 같은 방향명이 다시 나타나더라도 사이의 다른 방향 구간을 건너뛰지 않는다.
    o['segment']=o.direction.ne(o.direction.shift()).cumsum()
    o['direction_label']=o.direction+' 방면 · 구간 '+o.segment.astype(str)
    o['repeated_stop']=o.station.duplicated(keep=False)
    o=o.rename(columns={'station':'std_bus_sttn_id'})
    o=o.merge(summary,on='std_bus_sttn_id',how='left',validate='many_to_one')
    o['통계 연결']=o['순승차'].notna()
    o['승차 집중']=o['승차 집중'].fillna(False).astype(bool)
    o['sttn_nm']=o.sttn_nm.fillna(o.stationNm)
    # 각 통과 차수에 고유한 표시명을 부여한다.
    o['정류장']=o.stop_sequence.astype(str)+'. '+o.sttn_nm+' ['+o.std_bus_sttn_id+']'
    return o

def previous_candidates(ordered, idx):
    target=ordered.iloc[idx]
    if pd.isna(target['순승차']) or bool(target.get('repeated_stop',False)):
        return ordered.iloc[:0]
    candidates=[]
    for start in range(max(0,idx-2),idx):
        span=ordered.iloc[start:idx+1]
        if not span.stop_sequence.diff().iloc[1:].eq(1).all(): continue
        if 'segment' in span and span.segment.nunique()!=1: continue
        if 'direction' in span and (span.direction.nunique()!=1 or span.direction.eq('방향 미확인').any()): continue
        if 'transYn' in span and span.transYn.eq('Y').any(): continue
        if 'repeated_stop' in span and span.repeated_stop.any(): continue
        if span['순승차'].isna().any(): continue
        if span.iloc[0]['순승차'] >= target['순승차']: continue
        candidates.append(start)
    return ordered.iloc[candidates]
