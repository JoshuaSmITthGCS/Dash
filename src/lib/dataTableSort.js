/**
 * Comparator used by every sortable table in the app.
 *
 * Nulls always sort last regardless of direction. A name with no cost estimate is
 * not the cheapest name in the book, and letting it sort to the top of an
 * ascending cost column is exactly the reading error the cost columns exist to
 * prevent. This rule was previously implemented once inside SwingScreen; it is
 * shared so that every table answers "what does a missing value mean" the same
 * way.
 */
export const compareBy = (accessor, dir) => (left, right) => {
  const a = accessor(left)
  const b = accessor(right)
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'string' || typeof b === 'string') {
    return dir === 'asc' ? String(a).localeCompare(String(b)) : String(b).localeCompare(String(a))
  }
  return dir === 'asc' ? a - b : b - a
}

/** Sort `rows` by the column whose `key` matches `sort.key`. Unknown key = unsorted. */
export function sortRows(rows, columns, sort) {
  if (!sort?.key) return rows
  const column = columns.find((item) => item.key === sort.key)
  if (!column) return rows
  const accessor = column.sortValue || ((row) => row[column.key])
  return [...rows].sort(compareBy(accessor, sort.dir === 'asc' ? 'asc' : 'desc'))
}

/** Toggle direction when the same column is clicked again, otherwise start descending. */
export function nextSort(sort, key, defaultDir = 'desc') {
  if (sort?.key !== key) return { key, dir: defaultDir }
  return { key, dir: sort.dir === 'asc' ? 'desc' : 'asc' }
}
