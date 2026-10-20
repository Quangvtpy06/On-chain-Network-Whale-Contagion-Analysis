"""Independent reference equations used by the T09 release validator."""
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix

METRICS = ['in_degree','out_degree','degree','in_strength_usdt','out_strength_usdt',
           'weighted_degree_usdt','in_tx_count','out_tx_count','weighted_degree_tx','net_inflow_usdt']


def node_reference(edges):
    out = edges.groupby(['time_window','from_address']).agg(
        out_degree=('to_address','size'),out_strength_usdt=('total_value','sum'),out_tx_count=('transaction_count','sum'))
    inc = edges.groupby(['time_window','to_address']).agg(
        in_degree=('from_address','size'),in_strength_usdt=('total_value','sum'),in_tx_count=('transaction_count','sum'))
    out.index.names = inc.index.names = ['time_window','address']
    ref = out.join(inc,how='outer').fillna(0).sort_index()
    ref['degree'] = ref.in_degree+ref.out_degree
    ref['weighted_degree_usdt'] = ref.in_strength_usdt+ref.out_strength_usdt
    ref['weighted_degree_tx'] = ref.in_tx_count+ref.out_tx_count
    ref['net_inflow_usdt'] = ref.in_strength_usdt-ref.out_strength_usdt
    return ref


def compare(remote, edges, window_type, source, alpha=0.85, pagerank_tolerance=None):
    ref = node_reference(edges)
    actual = remote.set_index(['time_window','address']).sort_index()
    actual.index = actual.index.set_levels([x.astype(str) for x in actual.index.levels])
    ref.index = ref.index.set_levels([x.astype(str) for x in ref.index.levels])
    joined = actual.join(ref, how='outer', lsuffix='_actual',rsuffix='_reference')
    missing_remote = ~joined.index.isin(actual.index)
    extra_remote = ~joined.index.isin(ref.index)
    mismatch = {}
    for name in METRICS:
        mismatch[name] = ~np.isclose(joined[name+'_actual'],joined[name+'_reference'],
                                     rtol=1e-12,atol=1e-4,equal_nan=False)
    flags = pd.DataFrame(mismatch,index=joined.index)
    flags['missing_nodes'] = missing_remote
    flags['extra_nodes'] = extra_remote
    counts = flags.groupby(level=0).sum().astype(int)
    groups = {w:sub for w,sub in edges.groupby('time_window')}
    rows = []
    for w, counts_row in counts.iterrows():
        sub = groups.get(w,edges.iloc[:0])
        observed = remote.loc[remote.time_window.eq(w)]
        graph_nodes = sorted(set(sub.from_address)|set(sub.to_address))
        lookup = {addr:i for i,addr in enumerate(graph_nodes)}
        residual = None
        if not counts_row['missing_nodes'] and not counts_row['extra_nodes'] and graph_nodes:
            n = len(graph_nodes)
            matrix = coo_matrix((sub.total_value.to_numpy(),
                (sub.from_address.map(lookup).to_numpy(),sub.to_address.map(lookup).to_numpy())),shape=(n,n)).tocsr()
            sums = np.asarray(matrix.sum(axis=1)).ravel()
            inv = np.divide(1.0,sums,out=np.zeros(n),where=sums>0)
            x = observed.set_index('address').pagerank.reindex(graph_nodes).to_numpy()
            expected = alpha*(matrix.T @ (x*inv)+x[sums==0].sum()/n)+(1-alpha)/n
            residual = float(np.abs(x-expected).sum())
        tolerance = pagerank_tolerance if pagerank_tolerance is not None else max(1e-12,len(graph_nodes)*1e-8)
        pagerank_ok = residual is not None and residual <= tolerance and np.isclose(observed.pagerank.sum(),1,atol=1e-12)
        row = dict(window_type=window_type,time_window=w,reference=source,
            nodes_remote=len(observed),nodes_reference=len(graph_nodes),
            edges_reference=len(sub),degree_edges_remote=int(observed.in_degree.sum()),
            volume_remote=float(observed.in_strength_usdt.sum()),volume_reference=float(sub.total_value.sum()),
            pagerank_residual_l1=np.nan if residual is None else residual,pagerank_residual_tolerance=tolerance,
            pagerank_reference_pass=bool(pagerank_ok))
        row.update({name+'_mismatches':int(value) for name,value in counts_row.items()})
        row['status']='PASS' if not counts_row.any() and pagerank_ok else 'FAIL'
        rows.append(row)
    return pd.DataFrame(rows)


