import {useState} from 'react';
import {api, errorMessage, listAll} from '../api/client';
import {ErrorBox, money, PageHeader, useLoad} from '../components/Common';
const load = () => listAll('/api/ondc/orders');
const transitions = ['packed', 'ready_for_pickup', 'picked_up', 'delivered', 'fulfillment_failed'];
export default function Orders() {
  const {data = [], loading, error, reload} = useLoad(load);
  const [token, setToken] = useState(''); const [actionError, setActionError] = useState('');
  const mutate = async (path, body) => {setActionError(''); try {await api.post(path, body, {headers:{'X-Admin-Token':token}}); reload();} catch (requestError) {setActionError(errorMessage(requestError));}};
  return <><PageHeader title="Orders" action={<button className="secondary" onClick={reload}>Refresh</button>}>ONDC fulfillment, return and accounting operations without unnecessary customer details.</PageHeader><ErrorBox>{error || actionError}</ErrorBox><section className="panel">
    <div className="table-toolbar"><h2>ONDC orders <span className="count">{data?.length || 0}</span></h2><input type="password" aria-label="Admin token" placeholder="Admin token for actions" value={token} onChange={event=>setToken(event.target.value)}/></div>
    {loading ? <p role="status">Loading orders...</p> : data?.length ? data.map(order => <details className="order-detail" key={order.id}><summary><strong>{order.id}</strong> · {money(order.amount)} · <span className="badge">{order.state}</span> · {order.fulfillment_state}</summary>
      <div className="table-wrap"><table><thead><tr><th>Item</th><th>Quantity</th><th>Unit price</th><th>Total</th></tr></thead><tbody>{order.items.map(item=><tr key={item.item_id}><td>{item.item_id}</td><td>{item.quantity}</td><td>{money(item.unit_price)}</td><td>{money(item.total_price)}</td></tr>)}</tbody></table></div>
      <div className="form-actions">{transitions.map(target=><button className="secondary" key={target} disabled={!token} onClick={()=>mutate(`/api/ondc/orders/${order.id}/transitions`,{target,idempotency_key:`${target}-${Date.now()}`})}>{target.replaceAll('_',' ')}</button>)}</div>
      <h3>State history</h3><ul>{order.history.map((event,index)=><li key={index}>{event.from_state} → {event.to_state} ({event.fulfillment_state})</li>)}</ul>
      <h3>Financial audit</h3><ul>{order.financial_events.map((event,index)=><li key={index}>{event.event_type}: {money(event.amount)} · {event.status}</li>)}</ul>
      <h3>Returns</h3>{order.returns.length ? <ul>{order.returns.map(item=><li key={item.request_id}>{item.request_id}: {item.item_id}, qty {item.quantity} · {item.state}{item.state==='Return_Initiated'&&<span> <button disabled={!token} onClick={()=>mutate(`/api/ondc/orders/${order.id}/returns/${item.request_id}/decision`,{decision:'approve'})}>Approve</button> <button className="secondary" disabled={!token} onClick={()=>mutate(`/api/ondc/orders/${order.id}/returns/${item.request_id}/decision`,{decision:'reject'})}>Reject</button></span>}</li>)}</ul>:<p className="muted">No return requests.</p>}
    </details>) : <div className="empty"><h2>No confirmed ONDC orders</h2><p>Orders appear here after a valid confirm flow commits inventory.</p></div>}
  </section></>;
}
