import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import AuditTable, { type AuditRow } from "../../components/AuditTable";
import { LoadError, Pager, TableSkeleton } from "../../components/ui";

export default function AuditPage() {
  const [page, setPage] = useState(1);
  const data = useQuery({
    queryKey: ["audit", page],
    queryFn: () => api<{ items: AuditRow[]; total: number }>(
      `/api/audit?page=${page}&page_size=50`,
    ),
    placeholderData: keepPreviousData,
  });

  if (data.isError) return <LoadError onRetry={() => data.refetch()} />;

  return (
    <>
      <p className="hint mb-3">
        Кто и что менял в салоне. Действия нашей поддержки помечены отдельно — вы видите
        их так же, как свои.
      </p>
      {data.isLoading ? (
        <TableSkeleton rows={8} cols={5} />
      ) : (
        <>
          <AuditTable rows={data.data?.items ?? []} />
          <Pager page={page} total={data.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}
    </>
  );
}
