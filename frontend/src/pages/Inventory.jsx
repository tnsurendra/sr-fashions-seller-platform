import {useState} from 'react';
import {api, errorMessage, listAll} from '../api/client';
import {ErrorBox, PageHeader, useLoad} from '../components/Common';
const load = async () => {const [inventory, products, stores] = await Promise.all(['/api/inventory','/api/products','/api/stores'].map(listAll)); return {inventory,products,stores};};
function StockEditor({row, onSaved}) {
  const [quantity,setQuantity] = useState(row.quantity); const [saving,setSaving]=useState(false); const [error,setError]=useState('');
  async function save(event) {
    event.preventDefault(); setSaving(true); setError('');
    try {await api.put(`/api/inventory/${row.id}`, {quantity:Number(quantity)}); onSaved();} catch(error) {setError(errorMessage(error));} finally {setSaving(false);}
  }
  return <><form className="stock-editor" onSubmit={save}><input aria-label={`Stock for inventory ${row.id}`} type="number" min="0" max="2147483647" step="1" required value={quantity} onChange={e=>setQuantity(e.target.value)}/><button className="secondary" disabled={saving || Number(quantity)===row.quantity}>{saving ? 'Saving...':'Save'}</button></form><ErrorBox>{error}</ErrorBox></>;
}
export default function Inventory() {
  const {data,loading,error,reload} = useLoad(load); const [store,setStore] = useState('');
  const variants=new Map(data?.products.flatMap(product=>product.variants.map(variant=>[variant.id,{...variant,name:product.name}])) || []);
  const stores=new Map(data?.stores.map(row=>[row.id,row.name]) || []);
  const rows=data?.inventory.filter(row=>!store || row.store_id===Number(store)) || [];
  return <><PageHeader title="Inventory">Keep every size, color and store in stock.</PageHeader><ErrorBox>{error}</ErrorBox><section className="panel"><div className="table-toolbar"><h2>Stock by location</h2><select aria-label="Filter by store" value={store} onChange={e=>setStore(e.target.value)}><option value="">All stores</option>{data?.stores.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select><button className="secondary" onClick={reload}>Refresh</button></div>{loading ? <p role="status">Loading inventory...</p> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Product / SKU</th><th>Variant</th><th>Store</th><th>Status</th><th>Stock on hand</th></tr></thead><tbody>{rows.map(row=>{const variant=variants.get(row.variant_id);return <tr key={row.id}><td><strong>{variant?.name || `Variant #${row.variant_id}`}</strong><small>{variant?.sku}</small></td><td>{variant?.color} / {variant?.size}</td><td>{stores.get(row.store_id)}</td><td><span className={`badge ${row.quantity===0?'warning':''}`}>{row.quantity===0?'Out of stock':'In stock'}</span></td><td><StockEditor key={`${row.id}-${row.quantity}`} row={row} onSaved={reload}/></td></tr>;})}</tbody></table></div>:<div className="empty"><h2>No inventory yet</h2><p>Add a product with a store and opening stock to get started.</p></div>}</section><p className="help">Stock updates replace the current quantity. Refresh before editing if another admin is working.</p></>;
}
