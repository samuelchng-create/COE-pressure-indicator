import streamlit as st
import pandas as pd
import numpy as np
import requests
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.linear_model import Ridge

st.set_page_config(page_title='Singapore COE Pressure Index', layout='wide')
st.title('Singapore COE Pressure Index')
st.caption('Experimental public-interest tracker • Structural back-test + dealer-signal layer')

DATASET='d_69b3380ad7e51aff3a7dcc84eba52b8a'
URL=f'https://data.gov.sg/api/action/datastore_search?resource_id={DATASET}&limit=5000'

@st.cache_data(ttl=3600)
def load_coe():
    r=requests.get(URL,timeout=20); r.raise_for_status()
    rec=r.json()['result']['records']
    df=pd.DataFrame(rec)
    # tolerate API naming/case differences
    df.columns=[c.lower().strip().replace(' ','_') for c in df.columns]
    for c in ['quota','bids_success','bids_received','premium']:
        df[c]=pd.to_numeric(df[c],errors='coerce')
    df['bidding_no']=pd.to_numeric(df['bidding_no'],errors='coerce')
    df['date']=pd.to_datetime(df['month'].astype(str)+'-01') + pd.to_timedelta((df['bidding_no'].fillna(1)-1)*14,unit='D')
    return df.sort_values(['vehicle_class','date'])

def features(g):
    x=g.copy().sort_values('date')
    x['bid_pressure']=x['bids_received']/x['quota']
    x['excess_demand']=(x['bids_received']-x['quota'])/x['quota']
    x['premium_lag1']=x['premium'].shift(1)
    x['premium_lag2']=x['premium'].shift(2)
    x['momentum']=x['premium'].shift(1)-x['premium'].shift(2)
    x['bid_pressure_lag1']=x['bid_pressure'].shift(1)
    x['quota_lag1']=x['quota'].shift(1)
    x['month_num']=x['date'].dt.month
    return x.dropna().copy()

def walk_forward(g,min_train=36):
    x=features(g)
    cols=['premium_lag1','premium_lag2','momentum','bid_pressure_lag1','quota_lag1','month_num']
    preds=[]
    for i in range(min_train,len(x)):
        train=x.iloc[:i]; test=x.iloc[[i]]
        model=Ridge(alpha=10.0)
        model.fit(train[cols],train['premium'])
        p=float(model.predict(test[cols])[0])
        preds.append({'date':test.iloc[0]['date'],'actual':float(test.iloc[0]['premium']),'predicted':p,
                      'prev':float(test.iloc[0]['premium_lag1'])})
    return pd.DataFrame(preds)

def metrics(bt):
    if bt.empty: return {}
    mae=mean_absolute_error(bt.actual,bt.predicted)
    rmse=mean_squared_error(bt.actual,bt.predicted)**0.5
    naive=mean_absolute_error(bt.actual,bt.prev)
    actual_dir=np.sign(bt.actual-bt.prev); pred_dir=np.sign(bt.predicted-bt.prev)
    acc=float((actual_dir==pred_dir).mean())
    return {'MAE':mae,'RMSE':rmse,'Naive MAE':naive,'Direction accuracy':acc,'MAE uplift vs naive':(naive-mae)/naive if naive else np.nan}

try:
    df=load_coe()
except Exception as e:
    st.error(f'Could not load data.gov.sg data: {e}')
    st.stop()

cats=['Category A','Category B','Category D']
tabs=st.tabs(cats+['Dealer signals','Methodology'])
for tab,cat in zip(tabs[:3],cats):
    with tab:
        g=df[df.vehicle_class==cat]
        latest=g.iloc[-1]
        prev=g.iloc[-2]
        pressure=latest.bids_received/latest.quota
        c1,c2,c3,c4=st.columns(4)
        c1.metric('Latest COE',f"S${latest.premium:,.0f}",f"{latest.premium-prev.premium:+,.0f}")
        c2.metric('Bid / quota',f"{pressure:.2f}×")
        c3.metric('Bids received',f"{latest.bids_received:,.0f}")
        c4.metric('Quota',f"{latest.quota:,.0f}")
        chart=g.set_index('date')[['premium']].rename(columns={'premium':'COE premium'})
        st.line_chart(chart)
        bt=walk_forward(g)
        m=metrics(bt)
        st.subheader('Walk-forward structural back-test')
        a,b,c,d=st.columns(4)
        a.metric('Direction accuracy',f"{m.get('Direction accuracy',np.nan):.1%}")
        b.metric('MAE',f"S${m.get('MAE',np.nan):,.0f}")
        c.metric('Naïve MAE',f"S${m.get('Naive MAE',np.nan):,.0f}")
        d.metric('MAE improvement',f"{m.get('MAE uplift vs naive',np.nan):.1%}")
        if not bt.empty:
            show=bt.set_index('date')[['actual','predicted']].rename(columns={'actual':'Actual','predicted':'Walk-forward forecast'})
            st.line_chart(show)
            st.caption('Each prediction is generated using only observations preceding that tender. This is the structural benchmark; dealer signals are evaluated separately.')

with tabs[3]:
    st.subheader('Dealer Pressure observations')
    st.write('Upload a CSV of weekly dealer observations. This layer is deliberately separate so we can test whether dealer behaviour adds out-of-sample predictive value beyond the structural benchmark.')
    template=pd.DataFrame(columns=['observation_date','category','brand','model','advertised_price','coe_rebate_level','guaranteed_coe','number_of_bids','cash_discount','finance_rebate','trade_in_bonus','other_incentive_value','promotion_deadline','notes'])
    st.download_button('Download dealer-data template',template.to_csv(index=False).encode(),'dealer_observations_template.csv','text/csv')
    up=st.file_uploader('Upload dealer observations CSV',type='csv')
    if up:
        dd=pd.read_csv(up)
        st.dataframe(dd,use_container_width=True)
        st.info('Next model version will derive dealer-pressure features and compare structural-only vs structural+dealer walk-forward performance.')

with tabs[4]:
    st.subheader('Methodological principles')
    st.markdown('''
- **No hindsight:** walk-forward validation only.
- **Benchmark first:** forecasts must beat persistence (next COE = current COE).
- **Dealer uplift test:** dealer variables are retained only if they improve out-of-sample performance.
- **Separate categories:** A, B and D are modelled independently.
- **Transparent uncertainty:** eventual public forecasts should be ranges/probabilities, not false-precision point estimates.
- **Frozen prospective forecasts:** once public, every forecast should be timestamped and retained by model version.
''')
    st.caption('Experimental analysis, not financial advice. Source: LTA COE Bidding Results / Prices via data.gov.sg.')
