import { Emoji } from './Emoji'
import { BurgerIcon, CrossIcon } from './Icons'

/** The burger button (top-right of the home screen) and the right-side sheet it opens. */
export function Menu({
  open,
  onOpen,
  onClose,
  onLessons,
}: {
  open: boolean
  onOpen: () => void
  onClose: () => void
  onLessons: () => void
}) {
  return (
    <>
      <button type="button" className="x burger" aria-label="Меню" onClick={onOpen}>
        <BurgerIcon />
      </button>
      {open && (
        <>
          <div className="scrim" onClick={onClose} />
          <nav className="sheet" aria-label="Меню">
            <button type="button" className="x" aria-label="Закрыть" onClick={onClose}>
              <CrossIcon />
            </button>
            <button type="button" className="mi on" onClick={onLessons}>
              <Emoji value="📚" alt="" />
              <span className="t">Уроки</span>
            </button>
            <div className="mi off" aria-disabled="true">
              <Emoji value="⚙️" alt="" />
              <span className="t">
                Настройки
                <small>скоро</small>
              </span>
            </div>
          </nav>
        </>
      )}
    </>
  )
}
