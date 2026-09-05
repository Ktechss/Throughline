import React from "react";
import { ShieldAlert, Upload } from "lucide-react";
import { Button } from "@/components/ui/modal";

// THE CASE THE FACE GATE USED TO LET PAST.
//
// Studio's picker fires only when there are candidates to pick from. With none,
// the gate did nothing and the studio rendered normally — every tab clickable,
// every generation failing with a 400 on the missing reference, and no
// explanation anywhere.
//
// It deliberately does NOT offer "generate faces": /api/calibrate/faces refuses
// without a calibration seed, and a character in this state has none. An upload
// is the one thing that actually works, so it is the one thing offered.
export default function NoFacesPanel({ name, onUpload }) {
  return (
    <div className="min-h-screen grid place-items-center px-6">
      <div className="max-w-[440px] text-center">
        <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-full bg-rose-500/10 ring-1 ring-rose-500/30">
          <ShieldAlert className="h-5 w-5 text-rose-300" />
        </div>
        <h1 className="text-[16px] font-semibold text-zinc-100">
          {name || "She"} has no face yet
        </h1>
        <p className="mt-2 text-[12px] text-zinc-500 leading-relaxed">
          There are no generated candidates to choose from either, so there is
          nothing to pick. Every shot needs a master reference — until she has
          one, nothing in the studio can render.
        </p>
        <p className="mt-2 text-[12px] text-zinc-500 leading-relaxed">
          Upload one from her Bio tab and it becomes her reference.
        </p>
        <div className="mt-5 flex justify-center">
          <Button variant="primary" onClick={onUpload}>
            <Upload className="h-3.5 w-3.5" /> Upload her face
          </Button>
        </div>
      </div>
    </div>
  );
}
