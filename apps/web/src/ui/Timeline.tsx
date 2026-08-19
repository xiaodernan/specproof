import { StatusDot, type DotStatus } from "./StatusDot";

export interface TimelineEvent {
  id: string;
  title: string;
  description?: string;
  time?: string;
  status?: DotStatus;
}

export interface TimelineProps {
  events: TimelineEvent[];
}

export function Timeline(props: TimelineProps): JSX.Element {
  return (
    <div className="ui-timeline">
      {props.events.map((ev) => (
        <div className="ui-timeline-item" key={ev.id}>
          <div className="ui-timeline-rail">
            <StatusDot status={ev.status ?? "neutral"} size="sm" />
          </div>
          <div className="ui-timeline-content">
            <div className="ui-timeline-title">{ev.title}</div>
            {ev.description ? <div className="ui-timeline-desc">{ev.description}</div> : null}
            {ev.time ? <div className="ui-timeline-time">{ev.time}</div> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
