"use client";

/**
 * Who is going to see this image. The whole point of the app: the same photo gets a
 * different mask set depending on the answer, and the user picks before anything runs.
 */

import {
  DESTINATIONS,
  DESTINATION_BLURBS,
  DESTINATION_LABELS,
  type Destination,
} from "../lib/types.ts";

type Props = {
  value: Destination;
  onChange: (value: Destination) => void;
  disabled?: boolean;
};

export default function DestinationPicker({ value, onChange, disabled }: Props) {
  return (
    <fieldset className="destinations" disabled={disabled}>
      <legend>Where is this going?</legend>
      {DESTINATIONS.map((d) => (
        <label
          key={d}
          className={`destination${value === d ? " destination-on" : ""}`}
        >
          <input
            type="radio"
            name="destination"
            value={d}
            checked={value === d}
            onChange={() => onChange(d)}
          />
          <span className="destination-name">{DESTINATION_LABELS[d]}</span>
          <span className="destination-blurb">{DESTINATION_BLURBS[d]}</span>
        </label>
      ))}
    </fieldset>
  );
}
