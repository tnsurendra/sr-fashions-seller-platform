import {useState} from 'react';
import {Link} from 'react-router-dom';
import {listAll} from '../api/client';
import {ErrorBox, money, PageHeader, useLoad} from '../components/Common';
const load = () => listAll('/api/products');
export default function Products() {
  const {data, loading, error, reload} = useLoad(load); const [search,setSearch] = useState('');
  const rows = data?.filter(row => `${row.name} ${row.brand} ${row.variants.map(v=>v.sku).join(' ')}`.toLowerCase().includes(search.toLowerCase())) || [];
  return <><PageHeader title="Products" action={<Link className="button" to="/products/new">+ Add product</Link>}>The details that make your collection yours.</PageHeader><ErrorBox>{error}</ErrorBox><section className="panel"><div className="table-toolbar"><h2>Product catalog <span className="count">{data?.length || 0}</span></h2><input aria-label="Search products" placeholder="Search name, brand or SKU..." value={search} onChange={e=>setSearch(e.target.value)}/><button className="secondary" onClick={reload}>Refresh</button></div>{loading ? <p role="status">Loading products...</p> : rows.length ? <div className="table-wrap"><table><thead><tr><th>Product</th><th>Category</th><th>SKU / variant</th><th>MRP</th><th>Selling price</th></tr></thead><tbody>{rows.flatMap(product=>product.variants.map(variant=><tr key={variant.id}><td><strong>{product.name}</strong><small>{product.brand}</small></td><td><span className="badge">{product.category}</span></td><td>{variant.sku}<small>{variant.color} / {variant.size}</small></td><td className="muted">{money(variant.mrp)}</td><td><strong>{money(variant.selling_price)}</strong></td></tr>))}</tbody></table></div> : <div className="empty"><h2>{search ? 'No matching products' : 'Your collection starts here'}</h2><p>{search ? 'Try another name, brand or SKU.' : 'Add your first product with size, color and opening stock.'}</p><Link className="text-link" to="/products/new">Add a product &rarr;</Link></div>}</section></>;
}
