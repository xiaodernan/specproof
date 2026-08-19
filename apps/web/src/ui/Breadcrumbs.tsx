import { ChevronRightIcon } from "./icons";

export interface CrumbItem {
  label: string;
  href?: string;
}

export interface BreadcrumbsProps {
  items: CrumbItem[];
}

export function Breadcrumbs(props: BreadcrumbsProps): JSX.Element {
  return (
    <nav aria-label="Breadcrumb" className="ui-breadcrumbs">
      <ol>
        {props.items.map((item, i) => {
          const last = i === props.items.length - 1;
          return (
            <li
              key={i}
              className={last ? "ui-breadcrumb-current" : undefined}
              aria-current={last ? "page" : undefined}
            >
              {item.href && !last ? <a href={item.href}>{item.label}</a> : item.label}
              {!last ? (
                <span className="ui-breadcrumb-sep" aria-hidden="true">
                  <ChevronRightIcon size={10} />
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
