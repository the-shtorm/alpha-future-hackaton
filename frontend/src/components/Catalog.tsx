import {useMemo,useState} from 'react';
import type {Product} from '../types';
import {category,kind,matchesAmount,money,months,purposeNames,rate} from '../presentation';
import {Button,Empty,Field,Icon,Modal,Select} from './UI';

const categories:Record<string,string>={all:'Все продукты',working:'Оборотные средства',growth:'Развитие бизнеса',property:'Недвижимость',refinancing:'Рефинансирование'};
export function ProductCard({product,onDetails,onStart,children,recommended=false}:{product:Product;onDetails:(product:Product)=>void;onStart:(product:Product)=>void;children?:React.ReactNode;recommended?:boolean}){
 return <article className={`product-card ${recommended?'recommended':''}`}>
  <div className="product-top"><span className={`product-icon ${category(product)}`}><Icon name={product.policy.facility_kind==='OVERDRAFT'?'wallet':category(product)==='property'?'home':category(product)==='growth'?'brief':'spark'} size={25}/></span>{recommended?<span className="pill recommended-pill">По вашему запросу</span>:<span className="product-kind">{kind(product)}</span>}</div>
  <h3>{product.name}</h3><p className="product-purpose">{product.purposes.map(p=>purposeNames[p]??'Финансирование бизнеса').join(' · ')}</p>
  <div className="product-amount"><span>Сумма финансирования</span><strong>{money(product.minAmount)} — {money(product.maxAmount)}</strong></div>
  <dl className="product-metrics"><div><dt>Срок</dt><dd>{product.minTermMonths}–{months(product.maxTermMonths)}</dd></div><div><dt>Ставка</dt><dd>{rate(product.annualRatePct)}<small>{product.annualRatePct?'годовых':''}</small></dd></div></dl>
  <div className="product-tags"><span>{product.borrowerKinds.map(k=>k==='IP'?'ИП':'ООО').join(' и ')}</span><span>{product.policy.collateral?.required?'С имущественным залогом':'Без имущественного залога'}</span></div>
  {children}
  <div className="product-actions"><Button view={recommended?'accent':'primary'} size={48} block onClick={()=>onStart(product)}>Выбрать условия<Icon name="arrow" size={18}/></Button><button className="text-action" onClick={()=>onDetails(product)}>Подробнее</button></div>
 </article>;
}
export function ProductDetails({product,onClose,onStart}:{product:Product;onClose:()=>void;onStart:(product:Product)=>void}){
 const eligibility=product.policy.eligibility;
 return <Modal title={product.name} onClose={onClose} wide><div className="detail-subtitle"><span className="pill">{kind(product)}</span>{product.borrowerKinds.map(k=>k==='IP'?'Для ИП':'Для ООО').join(' · ')}</div>
  <div className="detail-numbers"><div><span>Сумма</span><strong>{money(product.minAmount)}–{money(product.maxAmount)}</strong></div><div><span>Срок</span><strong>{product.minTermMonths}–{months(product.maxTermMonths)}</strong></div><div><span>Ставка годовых</span><strong>{rate(product.annualRatePct)}</strong></div></div>
  <h3>Для каких задач</h3><div className="detail-purpose-list">{product.purposes.map(p=><span key={p}><Icon name="check" size={17}/>{purposeNames[p]??p}</span>)}</div>
  <h3>Основные условия</h3><ul className="detail-list">
   {eligibility?.min_business_age_months!==undefined&&<li>Бизнес работает не менее {months(eligibility.min_business_age_months)}.</li>}
   {eligibility?.min_average_monthly_revenue_rub!==undefined&&<li>Средняя выручка — от {money(eligibility.min_average_monthly_revenue_rub)} в месяц.</li>}
   {eligibility?.revenue_window_months!==undefined&&<li>Для проверки нужна выручка за {months(eligibility.revenue_window_months)}. Короткий период может потребовать уточнения.</li>}
   <li>{product.policy.collateral?.required?'Потребуется имущественный залог. Его наличие и приемлемость проверяются при оформлении.':'Имущественный залог не требуется по условиям этого продукта.'}</li>
   {Object.entries(product.policy.guarantor??{}).filter(([,value])=>value.endsWith('_REQUIRED')).map(([borrower])=><li key={borrower}>{borrower==='LLC'?'Для ООО':'Для ИП'} требуется поручительство.</li>)}
   {!!product.policy.collateral?.min_own_contribution_pct&&<li>Собственное участие — не менее {product.policy.collateral.min_own_contribution_pct}%.</li>}
   {eligibility?.extra_conditions?.includes('MARKETPLACE_6_MONTHS')&&<li>Продажи на маркетплейсе — от 6 месяцев.</li>}
   {eligibility?.extra_conditions?.includes('DEMO_BANK_ACCOUNT_6_MONTHS')&&<li>Расчётный счёт в банке — от 6 месяцев.</li>}
   {eligibility?.extra_conditions?.includes('MSP_REGISTRY')&&<li>Компания должна состоять в реестре МСП.</li>}
  </ul>
  <h3>Платежи и комиссии</h3><dl className="detail-fees"><div><dt>Тип ставки</dt><dd>{product.policy.pricing?.rate_type==='FIXED'?'Фиксированная':product.policy.pricing?.rate_type==='VARIABLE'?'Переменная':'По условиям продукта'}</dd></div><div><dt>Комиссия за выдачу</dt><dd>{money(product.policy.pricing?.issue_fee_rub)}</dd></div><div><dt>Обслуживание в месяц</dt><dd>{money(product.policy.pricing?.maintenance_fee_rub)}</dd></div></dl>
  <p className="fine-print">Проверка соответствия условиям не означает одобрение. Окончательные условия зависят от полной заявки. В текущем каталоге приведены демонстрационные условия.</p>
  <Button view="accent" size={56} block onClick={()=>onStart(product)}>Подобрать под мою задачу<Icon name="arrow" size={19}/></Button>
 </Modal>;
}
export function CatalogPage({products,loading,error,onRetry,onStart,onDetails}:{products:Product[];loading:boolean;error:string;onRetry:()=>void;onStart:(product?:Product)=>void;onDetails:(product:Product)=>void}){
 const [tab,setTab]=useState('all'),[search,setSearch]=useState(''),[amount,setAmount]=useState(''),[purpose,setPurpose]=useState('all'),[noCollateral,setNoCollateral]=useState(false);
 const filtered=useMemo(()=>products.filter(p=>(tab==='all'||category(p)===tab)&&(!search||p.name.toLocaleLowerCase('ru').includes(search.toLocaleLowerCase('ru')))&&matchesAmount(p,amount)&&(purpose==='all'||p.purposes.includes(purpose))&&(!noCollateral||!p.policy.collateral?.required)),[products,tab,search,amount,purpose,noCollateral]);
 const reset=()=>{setTab('all');setSearch('');setAmount('');setPurpose('all');setNoCollateral(false);};
 return <>
  <section className="catalog-hero"><div className="hero-copy"><span className="eyebrow"><span/>ФИНАНСИРОВАНИЕ БИЗНЕСА</span><h1>Ваш бизнес растёт.<br/>Найдём решение<br/><em>для следующего шага.</em></h1><p>На закупки, новое оборудование или развитие.<br/>Сравните продукты или подберите их под свою задачу.</p><div className="hero-actions"><Button view="accent" size={56} onClick={()=>onStart()}>Подобрать финансирование<Icon name="arrow" size={20}/></Button><a href="#catalog">Смотреть каталог ↓</a></div><div className="hero-caption"><Icon name="shield" size={17}/>Предварительный подбор без подачи заявки</div></div>
   <div className="hero-visual" aria-hidden="true"><div className="visual-circle"/><div className="visual-shadow-card"/><div className="visual-main-card"><span className="visual-brand">А</span><span className="visual-small">БИЗНЕС МОЖЕТ БОЛЬШЕ</span><strong>Следующая<br/>цель — ваша.</strong><div className="visual-line"><span/><span/><span/></div><Icon name="arrow" size={54}/></div><div className="visual-badge"><span><Icon name="check" size={20}/></span><div>Под вашу задачу<small>Понятные условия</small></div></div></div>
  </section>
  <div className="benefits-strip"><div><Icon name="brief"/><span>Для ИП и компаний<small>Продукты для разных этапов бизнеса</small></span></div><div><Icon name="wallet"/><span>Разные способы финансирования<small>Кредиты, линии и резерв на счёте</small></span></div><div><Icon name="file"/><span>Всё в одном кабинете<small>Подбор, условия и статус заявки</small></span></div></div>
  <section id="catalog" className="catalog-section"><div className="section-heading"><div><span className="eyebrow muted-eyebrow">ВЫБИРАЙТЕ ПОД СВОЮ ЗАДАЧУ</span><h2>Каталог финансирования</h2></div><span className="catalog-count">{products.length} продуктов в каталоге</span></div>
   <div className="category-tabs" role="group" aria-label="Категории продуктов">{Object.entries(categories).map(([key,text])=><button key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}>{text}</button>)}</div>
   <div className="catalog-filters"><Field label="Сумма, ₽" value={amount} onChange={setAmount}/><Select label="Цель финансирования" value={purpose} onChange={setPurpose} options={{all:'Любая цель',...purposeNames}}/><div className="search-field"><Icon name="search" size={20}/><input aria-label="Поиск продукта" placeholder="Найти продукт" value={search} onChange={e=>setSearch(e.target.value)}/></div></div>
   <div className="filter-caption"><label><input type="checkbox" checked={noCollateral} onChange={e=>setNoCollateral(e.target.checked)}/>Без имущественного залога</label><span>{loading?'Загружаем продукты…':`Найдено: ${filtered.length}`}{(tab!=='all'||search||amount||purpose!=='all'||noCollateral)&&<button className="text-action" onClick={reset}>Сбросить фильтры</button>}</span></div>
   {error?<Empty title="Не удалось загрузить каталог" action={<Button onClick={onRetry}>Повторить загрузку</Button>}>{error}</Empty>:loading?<div className="product-grid">{Array.from({length:6},(_,i)=><div className="catalog-skeleton" key={i}><span/><span/><span/></div>)}</div>:filtered.length?<div className="product-grid">{filtered.map(p=><ProductCard product={p} key={p.versionId} onDetails={onDetails} onStart={onStart}/>)}</div>:<Empty title="По этим условиям пока ничего нет" action={<Button view="secondary" onClick={reset}>Сбросить фильтры</Button>}>Попробуйте изменить сумму или цель. Можно также заполнить форму, чтобы проверить доступные варианты.</Empty>}
   <p className="catalog-disclosure">Условия каталога демонстрационные и не являются публичной офертой. Подбор продуктов не гарантирует одобрение кредита.</p>
  </section>
  <section className="bottom-cta"><div><span className="eyebrow">НЕ ЗНАЕТЕ, ЧТО ВЫБРАТЬ?</span><h2>Начните с задачи,<br/>а не с названия кредита.</h2><p>Расскажите о бизнесе — проверим условия и покажем подходящие варианты.</p></div><Button view="accent" size={56} onClick={()=>onStart()}>Помогите с выбором<Icon name="arrow" size={20}/></Button></section>
 </>;
}
