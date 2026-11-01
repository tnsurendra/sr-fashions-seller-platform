import {Link} from 'react-router-dom';
import {listAll} from '../api/client';
import {ErrorBox, PageHeader, useLoad} from '../components/Common';

const load = async () => {
  const orders = await listAll('/api/ondc/orders');
  return orders.flatMap(order => order.returns.map(item => ({...item, order_id: order.id})));
};

export default function Returns() {
  const {data: loadedData, loading, error, reload} = useLoad(load);
  const data = loadedData || [];
  return <><PageHeader title="Returns" action={<button className="secondary" onClick={reload}>Refresh</button>}>
    Supported ONDC return requests across confirmed orders. Decisions remain attached to the order audit trail.
  </PageHeader><ErrorBox>{error}</ErrorBox><section className="panel">
    <div className="table-toolbar"><h2>Return requests <span className="count">{data.length}</span></h2><Link className="button secondary" to="/orders">Open orders</Link></div>
    {loading ? <p role="status">Loading return requests...</p> : data.length ? <div className="table-wrap"><table><thead><tr><th>Request</th><th>Order</th><th>Item</th><th>Qty</th><th>Reason</th><th>Status</th><th>Requested</th></tr></thead><tbody>
      {data.map(item => <tr key={`${item.order_id}-${item.request_id}`}><td><strong>{item.request_id}</strong></td><td>{item.order_id}</td><td>{item.item_id}</td><td>{item.quantity}</td><td>{item.reason_id}</td><td><span className="badge">{item.state.replaceAll('_', ' ')}</span></td><td>{new Date(item.requested_at * 1000).toLocaleString()}</td></tr>)}
    </tbody></table></div> : <div className="empty"><h2>No return requests</h2><p>Eligible Buyer return updates appear here after a delivered ONDC order.</p></div>}
    <p className="help">Approve or reject an initiated request from its expanded order after entering the backend admin token.</p>
  </section></>;
}
