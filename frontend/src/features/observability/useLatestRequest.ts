import {useCallback, useRef} from 'react';

export function useLatestRequest() {
  const generationByKeyRef = useRef(new Map<string, number>());

  return useCallback((key: string) => {
    const generation = (generationByKeyRef.current.get(key) ?? 0) + 1;
    generationByKeyRef.current.set(key, generation);
    return () => generationByKeyRef.current.get(key) === generation;
  }, []);
}
