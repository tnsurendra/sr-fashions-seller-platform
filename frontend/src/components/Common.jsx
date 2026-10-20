import {useEffect, useState} from 'react';
import {errorMessage} from '../api/client';
export function useLoad(loader) {
  const [state, setState] = useState({data: null, error: '', loading: true});
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setState(previous => ({...previous, error: '', loading: true}));
    loader().then(data => {if (active) setState({data, error: '', loading: false});})
      .catch(error => {if (active) setState({data: null, error: errorMessage(error), loading: false});});
    return () => {active = false;};
  }, [loader, revision]);
  return {...state, reload: () => setRevision(value => value + 1)};
}
export function ErrorBox({children}) {return children ? <div className="error" role="alert">{children}</div> : null;}
export function PageHeader({eyebrow = 'RETAIL OPERATIONS', title, children, action}) {
  return <header className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{children}</p></div>{action}</header>;
}
export function Field({label, children}) {return <label className="field"><span>{label}</span>{children}</label>;}
export const money = value => new Intl.NumberFormat('en-IN', {style: 'currency', currency: 'INR'}).format(value);
