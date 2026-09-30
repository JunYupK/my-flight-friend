import { createContext } from "react";

/** 신선도 기준(분). TripPage가 view.window_minutes로 제공하고 StaleBadge가 읽는다 (LegCard 등 슬롯 props를 바꾸지 않기 위해). */
export const StaleWindowContext = createContext(240);
