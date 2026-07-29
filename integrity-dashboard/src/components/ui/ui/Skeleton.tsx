// @ts-nocheck
import React from 'react';

interface SkeletonProps {
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({ className = "" }) => {
  return (
    <div 
      className={`animate-pulse bg-white/5 rounded-md relative overflow-hidden ${className}`}
    >
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent -translate-x-full animate-[shimmer_2s_infinite]"></div>
    </div>
  );
};

export const CardSkeleton = () => (
  <div className="glass-card p-6 h-[220px] flex flex-col justify-between">
    <div className="flex justify-between items-start">
      <div className="space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-3 w-48" />
      </div>
      <Skeleton className="h-5 w-16" />
    </div>
    <div className="flex items-center gap-6">
      <Skeleton className="h-20 w-20 rounded-full" />
      <div className="flex-1 space-y-4">
        <div className="space-y-1">
          <Skeleton className="h-2 w-16" />
          <Skeleton className="h-3 w-24" />
        </div>
        <div className="space-y-1">
          <Skeleton className="h-2 w-24" />
          <Skeleton className="h-2 w-full" />
        </div>
      </div>
    </div>
  </div>
);
