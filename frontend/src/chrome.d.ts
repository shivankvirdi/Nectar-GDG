declare namespace chrome {
  namespace tabs {
    interface Tab {
      url?: string
    }

    interface QueryInfo {
      active?: boolean
      currentWindow?: boolean
    }

    function query(
      queryInfo: QueryInfo,
      callback: (tabs: Tab[]) => void,
    ): void
  }
}
