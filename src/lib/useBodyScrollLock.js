import { useEffect } from 'react'

// iOS Safari lets touch drags scroll the page behind a fixed-position overlay, so an open
// modal without this rubber-bands the body underneath it. A counter supports modals that can
// stack (e.g. password change opened from within another dialog).
let lockCount = 0
let savedScrollY = 0

export default function useBodyScrollLock(active = true) {
  useEffect(() => {
    if (!active) return undefined
    if (lockCount === 0) {
      savedScrollY = window.scrollY
      document.body.style.position = 'fixed'
      document.body.style.top = `-${savedScrollY}px`
      document.body.style.left = '0'
      document.body.style.right = '0'
      document.body.style.width = '100%'
    }
    lockCount += 1
    return () => {
      lockCount -= 1
      if (lockCount === 0) {
        document.body.style.position = ''
        document.body.style.top = ''
        document.body.style.left = ''
        document.body.style.right = ''
        document.body.style.width = ''
        window.scrollTo(0, savedScrollY)
      }
    }
  }, [active])
}
