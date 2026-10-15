import { Link } from "react-router";

import { Empty } from "../components/Status";

export function NotFoundPage() {
  return (
    <Empty>
      <h1>Страница не найдена</h1>
      <Link to="/">К списку экспериментов</Link>
    </Empty>
  );
}
