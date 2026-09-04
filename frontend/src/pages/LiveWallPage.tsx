import React, { useState } from 'react';
import type { Camera } from '../types/api';
import { CameraTile } from '../components/camera/CameraTile';
import { EventFeedRow } from '../components/camera/EventFeedRow';
import type { LiveEventItem } from '../hooks/usePollingSightings';
import { Video, AlertCircle, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useUploadStore } from '../stores/uploadStore';
import { staticAssetUrl } from '../lib/api';

/** Column count follows the number of live feeds: 1 full width, 2 side by side,
 *  3 or more in three columns. Tiles are never padded out with empty slots. */
function gridColumnsClass(feedCount: number): string {
  if (feedCount <= 1) return 'grid-cols-1';
  if (feedCount === 2) return 'grid-cols-1 md:grid-cols-2';
  return 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3';
}

interface LiveWallPageProps {
  cameras: Camera[];
  events: LiveEventItem[];
  flashingCameraCode?: string | null;
}

export const LiveWallPage: React.FC<LiveWallPageProps> = ({
  cameras,
  events,
  flashingCameraCode,
}) => {
  const [selectedCameraCode, setSelectedCameraCode] = useState<string | null>(null);
  const getVideoUrl = useUploadStore(s => s.getVideoUrl);

  const handleTileClick = (cameraCode: string) => {
    setSelectedCameraCode((prev) => (prev === cameraCode ? null : cameraCode));
  };

  const filteredEvents = selectedCameraCode
    ? events.filter((e) => e.cameraCode === selectedCameraCode)
    : events;

  return (
    <div className="flex-1 flex flex-col md:flex-row h-full overflow-hidden bg-[var(--surface-base)]">
      {/* Camera Grid (Left ~2/3) */}
      <section className="flex-1 flex flex-col p-4 overflow-y-auto border-r border-[var(--border-subtle)]">
        {/* Section Header */}
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-[var(--border-subtle)]">
          <div className="flex items-center gap-2">
            <Video className="w-4 h-4 text-[var(--text-secondary)]" />
            <h1 className="text-sm font-semibold text-[var(--text-primary)]">
              Live camera feeds
            </h1>
            <span className="text-xs font-mono text-[var(--text-secondary)] bg-[var(--surface-sunken)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
              {cameras.length} {cameras.length === 1 ? 'feed' : 'feeds'}
            </span>
          </div>

          {selectedCameraCode && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-secondary)]">Filtered by:</span>
              <button
                onClick={() => setSelectedCameraCode(null)}
                className="text-xs font-mono px-2 py-0.5 rounded bg-[var(--accent)] text-[var(--text-inverse)] hover:bg-[var(--accent-hover)] cursor-pointer"
              >
                {selectedCameraCode} ×
              </button>
            </div>
          )}
        </div>

        {/* Camera Grid — one tile per uploaded video, never an empty slot */}
        {cameras.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-12 text-center">
            <Video className="w-10 h-10 text-[var(--text-muted)] mb-3" />
            <p className="text-sm font-medium text-[var(--text-primary)]">No video uploaded yet.</p>
            <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-[320px]">
              Upload a clip and the camera it was recorded on appears here as a live feed.
            </p>
            <Link
              to="/upload"
              className="mt-4 flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-[var(--accent)] text-[var(--text-inverse)] rounded-[var(--radius-sm)] hover:bg-[var(--accent-hover)] cursor-pointer"
            >
              <Upload className="w-4 h-4" />
              Upload video
            </Link>
          </div>
        ) : (
          <div className={`grid ${gridColumnsClass(cameras.length)} gap-4`}>
            {cameras.map((camera) => (
              <CameraTile
                key={camera.id}
                camera={camera}
                isFlashing={flashingCameraCode === camera.code}
                isSelected={selectedCameraCode === camera.code}
                onClick={() => handleTileClick(camera.code)}
                /* Local blob first for instant playback right after upload,
                   then the server copy so the feed survives a page reload. */
                videoUrl={getVideoUrl(camera.code) ?? staticAssetUrl(camera.video_url)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Live Event Feed (Right 360px fixed) */}
      <aside className="w-full md:w-[360px] shrink-0 flex flex-col h-full bg-[var(--surface-raised)]">
        <div className="p-3 border-b border-[var(--border-default)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
            <h2 className="text-xs font-semibold text-[var(--text-primary)] uppercase tracking-wider">
              Ingest & decision stream
            </h2>
          </div>
          <span className="text-[11px] font-mono text-[var(--text-secondary)]">
            {filteredEvents.length} events
          </span>
        </div>

        {/* Event List */}
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5">
          {filteredEvents.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-[var(--text-secondary)]">
              <AlertCircle className="w-6 h-6 text-[var(--text-muted)] mb-2" />
              <p className="text-xs font-medium text-[var(--text-primary)]">No events yet</p>
              <p className="text-[11px] text-[var(--text-secondary)] mt-1 max-w-[220px]">
                Start the pipeline with <code className="font-mono text-[var(--accent-text)]">./scripts/demo.sh</code> to begin processing.
              </p>
            </div>
          ) : (
            filteredEvents.map((evt) => <EventFeedRow key={evt.id} event={evt} />)
          )}
        </div>
      </aside>
    </div>
  );
};
