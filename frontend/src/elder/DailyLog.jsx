import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { SYMPTOM_ICONS } from '../ui/Icons'
import { greeting } from './ElderApp'

/* E1 — daily symptom log.
 *
 * Explicitly not a checklist. She taps only when something feels off, and the
 * intro copy says so, because a grid of six tiles otherwise reads as six things
 * to get through.
 *
 * Everything sits in one non-scrolling column: the six tiles plus the header
 * must fit 402 x 874 outright. Any type-scale change has to be re-checked
 * against that.
 */
export default function DailyLog({ person, onTap }) {
  const [tiles, setTiles] = useState([])

  useEffect(() => {
    api.symptoms().then(setTiles).catch(() => setTiles([]))
  }, [])

  const { part, eyebrow } = greeting(person.today)

  return (
    <div className="co-log">
      <header className="co-log__header">
        <p className="co-log__eyebrow">{eyebrow}</p>
        <h1 className="co-log__title">
          Good {part}, {person.name}.
        </h1>
        <p className="co-log__intro">
          {person.caregiver.name} is checking on you today. If something
          doesn&rsquo;t feel right, tap it. If you feel well, there&rsquo;s
          nothing to do.
        </p>
      </header>

      <div className="co-log__grid" role="group" aria-label="How are you feeling?">
        {tiles.map((tile) => {
          const Icon = SYMPTOM_ICONS[tile.id]
          return (
            <button
              key={tile.id}
              type="button"
              className="co-tile"
              onClick={() => onTap(tile)}
            >
              {Icon && <Icon />}
              <span className="co-tile__label">{tile.label}</span>
            </button>
          )
        })}
      </div>

      <p className="co-log__footer">
        {person.caregiver.name} set this up for you. Nothing else to do.
      </p>
    </div>
  )
}
