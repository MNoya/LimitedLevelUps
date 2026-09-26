import { restPassthrough } from "../_shared/public-data";

export const onRequestGet: PagesFunction = () => restPassthrough("public_sets?select=*&order=start_date.desc", 60 * 60);
